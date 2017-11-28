import os
import logging
from queue import Queue
from builtins import str
from future import standard_library

from pymesos import MesosSchedulerDriver, Scheduler
from addict import Dict

from airflow import configuration
from airflow.models import DagPickle
from airflow.executors.base_executor import BaseExecutor
from airflow.settings import Session
from airflow.utils.state import State
from airflow.exceptions import AirflowException

standard_library.install_aliases()

DEFAULT_FRAMEWORK_NAME = 'Airflow'
FRAMEWORK_CONNID_PREFIX = 'mesos_framework_'
DEFAULT_FRAMEWORK_ROLE = "*"
DEFAULT_TASK_PREFIX = "AirflowTask"

def get_role():
    if not configuration.get('mesos', 'FRAMEWORK_ROLE'):
        return DEFAULT_FRAMEWORK_ROLE
    return configuration.get('mesos', 'FRAMEWORK_ROLE')

def get_framework_name():
    if not configuration.get('mesos', 'FRAMEWORK_NAME'):
        return DEFAULT_FRAMEWORK_NAME
    return configuration.get('mesos', 'FRAMEWORK_NAME')

def get_task_prefix():
    if not configuration.get('mesos', 'TASK_PREFIX'):
        return DEFAULT_TASK_PREFIX
    return configuration.get('mesos', 'TASK_PREFIX')

def copy_env_var(command, env_var_name):
    if not isinstance(command.environment.variables, list):
        command.environment.variables = []
    command.environment.variables.append(
        dict(name=env_var_name, value=os.getenv(env_var_name, ''))
    )

def accepted_role(resource):
    return get_role() == '*' or get_role() == resource.role

# AirflowMesosScheduler, implements Mesos Scheduler interface
# To schedule airflow jobs on mesos
class AirflowMesosScheduler(Scheduler):
    """
    Airflow Mesos scheduler implements mesos scheduler interface
    to schedule airflow tasks on mesos.
    Basically, it schedules a command like
    'airflow run <dag_id> <task_instance_id> <start_date> --local -p=<pickle>'
    to run on a mesos slave.
    """

    def __init__(self,
                 task_queue,
                 result_queue,
                 task_cpu=1,
                 task_mem=256):
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.task_cpu = task_cpu
        self.task_mem = task_mem
        self.task_counter = 0
        self.task_key_map = {}

    def registered(self, driver, frameworkId, masterInfo):
        logging.info("AirflowScheduler registered to mesos with framework ID %s", frameworkId.value)

        if configuration.getboolean('mesos', 'CHECKPOINT') and configuration.get('mesos', 'FAILOVER_TIMEOUT'):
            # Import here to work around a circular import error
            from airflow.models import Connection

            # Update the Framework ID in the database.
            session = Session()
            conn_id = FRAMEWORK_CONNID_PREFIX + get_framework_name()
            connection = Session.query(Connection).filter_by(conn_id=conn_id).first()
            if connection is None:
                connection = Connection(conn_id=conn_id, conn_type='mesos_framework-id',
                                        extra=frameworkId.value)
            else:
                connection.extra = frameworkId.value

            session.add(connection)
            session.commit()
            Session.remove()

    def reregistered(self, driver, masterInfo):
        logging.info("AirflowScheduler re-registered to mesos")

    def disconnected(self, driver):
        logging.info("AirflowScheduler disconnected from mesos")

    def offerRescinded(self, driver, offerId):
        logging.info("AirflowScheduler offer %s rescinded", str(offerId))

    def frameworkMessage(self, driver, executorId, slaveId, message):
        logging.info("AirflowScheduler received framework message %s", message)

    def executorLost(self, driver, executorId, slaveId, status):
        logging.warning("AirflowScheduler executor %s lost", str(executorId))

    def slaveLost(self, driver, slaveId):
        logging.warning("AirflowScheduler slave %s lost", str(slaveId))

    def error(self, driver, message):
        logging.error("AirflowScheduler driver aborted %s", message)
        raise AirflowException("AirflowScheduler driver aborted %s" % message)

    def resourceOffers(self, driver, offers):
        for offer in offers:
            logging.info("offer: {}".format(offer))
            tasks = []
            offerCpus = 0
            offerMem = 0
            for resource in offer.resources:
                if resource.name == "cpus" and accepted_role(resource):
                    offerCpus += resource.scalar.value
                elif resource.name == "mem" and accepted_role(resource):
                    offerMem += resource.scalar.value

            logging.info(
                "Received offer {} with cpus: {} and mem: {}".format(
                    offer.id.value, offerCpus, offerMem))

            remainingCpus = offerCpus
            remainingMem = offerMem

            while (not self.task_queue.empty()) and \
                    remainingCpus >= self.task_cpu and \
                    remainingMem >= self.task_mem:
                key, cmd = self.task_queue.get()
                tid = self.task_counter
                self.task_counter += 1
                self.task_key_map[str(tid)] = key

                logging.info("Launching task %d using offer %s", tid, offer.id.value)

                task = Dict()
                task.task_id.value = str(tid)
                task.agent_id.value = offer.agent_id.value
                task.name = "{} {}".format(get_task_prefix(), tid)
                task.resources = [
                    dict(name="cpus", type="SCALAR", scalar={"value": self.task_cpu}, role=get_role()),
                    dict(name="mem", type="SCALAR", scalar={"value": self.task_mem}, role=get_role()),
                ]

                container = Dict()
                container.type = "DOCKER"
                container.volumes = [
                    dict(host_path="/var/run/docker.sock", container_path="/var/run/docker.sock", mode="RW"),
                ]

                docker = Dict()
                docker.image = os.getenv("DOCKER_AIRFLOW_IMAGE_TAG")
                docker.force_pull_image = True
                docker.network = "BRIDGE"
                docker.parameters = [
                    dict(key="label", value="ORGANIZATION_ID={}".format(get_task_prefix()))
                ]

                container.docker = docker
                task.container = container

                command = Dict()
                command.shell = False
                command.arguments = cmd.split()
                command.uris = [
                    dict(value='file:///etc/docker.tar.gz', extract=True, cache=False, executable=False)
                ]

                # Copy some environment vars from scheduler to execution docker container
                copy_env_var(command, "AIRFLOW__CORE__SQL_ALCHEMY_CONN")
                copy_env_var(command, "AIRFLOW__SMTP__SMTP_HOST")
                copy_env_var(command, "AIRFLOW__SMTP__SMTP_STARTTLS")
                copy_env_var(command, "AIRFLOW__SMTP__SMTP_SSL")
                copy_env_var(command, "AIRFLOW__SMTP__SMTP_USER")
                copy_env_var(command, "AIRFLOW__SMTP__SMTP_PORT")
                copy_env_var(command, "AIRFLOW__SMTP__SMTP_PASSWORD")
                copy_env_var(command, "AIRFLOW__SMTP__SMTP_MAIL_FROM")
                copy_env_var(command, "AWS_ACCESS_KEY_ID")
                copy_env_var(command, "AWS_SECRET_ACCESS_KEY")
                copy_env_var(command, "AWS_REGION")
                copy_env_var(command, "AWS_S3_TEMP_BUCKET")
                copy_env_var(command, "S3_ARTIFACT_PATH")
                copy_env_var(command, "AIRFLOW_CONN_S3_CONNECTION_LOGS")
                copy_env_var(command, "AIRFLOW__CORE__REMOTE_LOG_CONN_ID")
                copy_env_var(command, "AIRFLOW__CORE__REMOTE_BASE_LOG_FOLDER")
                copy_env_var(command, "AIRFLOW__CORE__DAG_CONCURRENCY")

                task.command = command
                tasks.append(task)
                remainingCpus -= self.task_cpu
                remainingMem -= self.task_mem

            if len(tasks) > 0:
                driver.launchTasks(offer.id, tasks)
            else:
                driver.declineOffer(offer.id)

    def statusUpdate(self, driver, update):
        logging.info("Task %s is in state %s, data %s",
                     update.task_id.value, update.state, update)

        try:
            key = self.task_key_map[update.task_id.value]
        except KeyError:
            # The map may not contain an item if the framework re-registered after a failover.
            # Discard these tasks.
            logging.warn("Unrecognised task key %s" % update.task_id.value)
            return

        if update.state == "TASK_FINISHED":
            self.result_queue.put((key, State.SUCCESS))
            self.task_queue.task_done()

        if update.state == "TASK_LOST" or \
           update.state == "TASK_KILLED" or \
           update.state == "TASK_FAILED" or \
           update.state == "TASK_ERROR":
            self.result_queue.put((key, State.FAILED))
            self.task_queue.task_done()


class AstronomerMesosExecutor(BaseExecutor):
    """
    MesosExecutor allows distributing the execution of task
    instances to multiple mesos workers.

    Apache Mesos is a distributed systems kernel which abstracts
    CPU, memory, storage, and other compute resources away from
    machines (physical or virtual), enabling fault-tolerant and
    elastic distributed systems to easily be built and run effectively.
    See http://mesos.apache.org/
    """

    def __init__(self, mesos_driver=None):
        super().__init__()
        self.task_queue = Queue()
        self.result_queue = Queue()
        self._mesos_driver = mesos_driver

    @property
    def mesos_driver(self):
        """
        Lazily instantiates the Mesos scheduler driver if one was not injected in
        via the constructor
        """
        if self._mesos_driver is None:
            framework = Dict()
            framework.user = 'core'

            if not configuration.get('mesos', 'MASTER'):
                logging.error("Expecting mesos master URL for mesos executor")
                raise AirflowException("mesos.master not provided for mesos executor")

            master = configuration.get('mesos', 'MASTER')

            framework.name = get_framework_name()
            framework.role = get_role()

            if not configuration.get('mesos', 'TASK_CPU'):
                task_cpu = 1
            else:
                task_cpu = configuration.getfloat('mesos', 'TASK_CPU')

            if not configuration.get('mesos', 'TASK_MEMORY'):
                task_memory = 256
            else:
                task_memory = configuration.getfloat('mesos', 'TASK_MEMORY')

            if configuration.getboolean('mesos', 'CHECKPOINT'):
                framework.checkpoint = True

                if configuration.get('mesos', 'FAILOVER_TIMEOUT'):
                    # Import here to work around a circular import error
                    from airflow.models import Connection

                    # Query the database to get the ID of the Mesos Framework, if available.
                    conn_id = FRAMEWORK_CONNID_PREFIX + framework.name
                    session = Session()
                    connection = session.query(Connection).filter_by(conn_id=conn_id).first()
                    if connection is not None:
                        # Set the Framework ID to let the scheduler reconnect with running tasks.
                        framework.id.value = connection.extra

                    framework.failover_timeout = configuration.getint('mesos', 'FAILOVER_TIMEOUT')
            else:
                framework.checkpoint = False

            logging.info('MesosFramework master : %s, name : %s, checkpoint : %s',
                         master, framework.name, str(framework.checkpoint))

            if configuration.getboolean('mesos', 'AUTHENTICATE'):
                if not configuration.get('mesos', 'DEFAULT_PRINCIPAL'):
                    logging.error("Expecting authentication principal in the environment")
                    raise AirflowException("mesos.default_principal not provided in authenticated mode")
                if not configuration.get('mesos', 'DEFAULT_SECRET'):
                    logging.error("Expecting authentication secret in the environment")
                    raise AirflowException("mesos.default_secret not provided in authenticated mode")

                principal = configuration.get('mesos', 'DEFAULT_PRINCIPAL')
                secret = configuration.get('mesos', 'DEFAULT_SECRET')

                framework.principal = credential.principal

                self._mesos_driver = MesosSchedulerDriver(
                    AirflowMesosScheduler(self.task_queue, self.result_queue, task_cpu, task_memory),
                    framework,
                    master,
                    use_addict=True,
                    principal=principal,
                    secret=secret)
            else:
                framework.principal = 'Airflow'
                self._mesos_driver = MesosSchedulerDriver(
                    AirflowMesosScheduler(self.task_queue, self.result_queue, task_cpu, task_memory),
                    framework,
                    master,
                    use_addict=True)
        return self._mesos_driver

    def start(self):
        self.mesos_driver.start()

    def execute_async(self, key, command, queue=None):
        self.task_queue.put((key, command))

    def sync(self):
        while not self.result_queue.empty():
            results = self.result_queue.get()
            self.change_state(*results)

    def end(self):
        self.task_queue.join()
        self.mesos_driver.stop()
