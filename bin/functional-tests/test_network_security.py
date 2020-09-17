import os
import sys
import logging
from random import randint
from time import sleep, time
from contextlib import contextmanager
import xml.etree.ElementTree as xml_parser

import pytest
import testinfra
from kubernetes import client, config

if os.environ.get('DEBUG'):
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
else:
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)

class ScanFinding():

    def __init__(self, name="", ip_address="", ports=[]):
        self.name = name
        self.ip_address = ip_address
        self.ports = ports

    def add_port(self, port):
        if not port in self.ports:
            self.ports.append(port)

class ScanResult():

    def __init__(self, findings=[]):
        self.findings = findings

    def add_finding(self, finding):
        self.findings.append(finding)

    def remove_finding(self, finding):
        self.findings.remove(finding)

class ScanTarget():

    def __init__(self, name, ip_address, _type, ports=[], namespace=None):
        self.name = name
        self.ip_address = ip_address
        assert isinstance(self.ip_address, str), \
            f"Expected to find str, but found: {type(ip_address)}"
        self._type = _type
        assert self._type in ["pod", "service"], \
            f"Expected to find 'pod' or 'service', but found {self._type}"
        self.ports = ports
        for port in self.ports:
            assert isinstance(port, int), \
                f"Expected to find int, but found: {type(port)}"
        self.namespace = namespace
        assert isinstance(self.namespace, str), \
            f"Expected to find str, but found: {type(self.namespace)}"


class KubernetesNetworkChecker():

    def __init__(self):
        config.load_kube_config()
        self.targets = []
        self.v1 = client.CoreV1Api()

    def collect_scan_targets(self):
        logging.info("Iterating through all pods")
        pods = self.v1.list_pod_for_all_namespaces(watch=False)
        for pod in pods.items:
            ip = pod.status.pod_ip
            if not ip:
                continue
            name = pod.metadata.name
            namespace = pod.metadata.namespace
            ports = []
            for container in pod.spec.containers:
                if not container.ports:
                    continue
                for port in container.ports:
                    ports.append(port.container_port)
            target = \
                ScanTarget(name, ip, "pod", ports=ports, namespace=namespace)
            if ports:
                self.targets.append(target)
        services = self.v1.list_service_for_all_namespaces(watch=False)
        for service in services.items:
            ip = service.spec.cluster_ip
            name = service.metadata.name
            namespace = service.metadata.namespace
            ports = []
            for port in service.spec.ports:
                ports.append(port.port)
            target = ScanTarget(name,
                                ip,
                                "service",
                                ports=ports,
                                namespace=namespace)
            if ports:
                self.targets.append(target)

    @contextmanager
    def _scanning_pod(self):
        namespace = 'astronomer-scan-test'
        pod_name = f'network-scanner-{randint(0,100000)}'
        v1container = client.V1Container(name='scanner')
        v1container.command = ["sleep", "300"]
        v1container.image = "alpine"
        v1podspec = client.V1PodSpec(containers=[v1container])
        v1objectmeta = client.V1ObjectMeta(name=pod_name)
        v1pod = client.V1Pod(spec=v1podspec,
                             metadata=v1objectmeta)
        logging.info(
            f"Creating {pod_name} pod in namespace {namespace}")
        # --as=system:serviceaccount:astronomer:default
        pod = self.v1.create_namespaced_pod(namespace, v1pod)
        # allow pod to become 'Pending'
        sleep(2)
        try:
            timeout = 120
            start = time()
            while True:
                if time() - start > timeout:
                    raise Exception("Timed out waiting for pod to start")
                sleep(1)
                check_pod = self.v1.read_namespaced_pod(
                    pod.metadata.name, namespace)
                if check_pod.status.container_statuses[0].ready:
                    logging.info("network-scanner is ready")
                    break
            test_fixture = testinfra.get_host(
                    f'kubectl://{pod.metadata.name}?' +
                    f'container={v1container.name}&namespace={namespace}')
            logging.info("Installing nmap into network-scanner")
            test_fixture.check_output('apk add nmap')
            test_fixture.exists('nmap')
            yield test_fixture
        finally:
            logging.info(
                f"Cleaning up network-scanner pod from namespace {namespace}")
            self.v1.delete_namespaced_pod(v1pod.metadata.name, namespace)

    def scan_all_targets(self):
        # Configure API key authorization: BearerToken
        all_ports = set()
        for target in self.targets:
            for port in target.ports:
                all_ports.add(port)
        all_ports = list(all_ports)
        all_ips = set()
        for target in self.targets:
            all_ips.add(target.ip_address)
        # Nmap does not have an option to specify ports-per-target,
        # so we scan all ports for any target on all hosts.
        with self._scanning_pod() as scanner:
            scanner.check_output('whoami')
            ports_string = ','.join([str(port) for port in all_ports])
            addresses_string = ' '.join(all_ips)
            logging.info("Executing scan...")
            command = "nmap --max-retries 2 -T5 --max-rtt-timeout 100ms " + \
                "-Pn -oX /scan-results.xml " + \
                f"-p{ports_string} {addresses_string}"
            logging.info(f"running command: {command}")
            start = time()
            scanner.check_output(command)
            duration = time() - start
            logging.info(f"Command took {duration} seconds")
            result = scanner.check_output("cat /scan-results.xml")
        root = xml_parser.fromstring(result)
        open_ports = {}
        for child in root:
            if child.tag == "host":
                ip_address = None
                for grandchild in child:
                    if grandchild.tag == "address":
                        ip_address = grandchild.attrib['addr']
                    if grandchild.tag == "ports":
                        # sample XML at the "ports" level:
                        # <ports>
                        #   <port protocol="tcp" portid="53">
                        #     <state state="closed" reason="reset" reason_ttl="253"/>
                        #     <service name="domain" method="table" conf="3"/>
                        #   </port>
                        #   <port protocol="tcp" portid="61678">
                        #     <state state="closed" reason="reset" reason_ttl="253"/>
                        #   </port>
                        # </ports>
                        for port in grandchild:
                            is_open = False
                            for state in port:
                                if not state.tag == "state":
                                    continue
                                is_open = state.attrib['state'] == "open"
                            if is_open:
                                if ip_address not in open_ports:
                                    open_ports[ip_address] = []
                                open_ports[ip_address].append(int(port.attrib['portid']))
        result = ScanResult()
        # def __init__(self, name, ip_address, ports=[]):
        for address in open_ports.keys():
            if not open_ports[address]:
                continue
            scan_finding = ScanFinding()
            scan_finding.ip_address = address
            for target in self.targets:
                if target.ip_address == address:
                    scan_finding.name = f"{target._type}/{target.name}"
                    print(f"{target._type} {target.name} ({address}):")
                    break
            for port in open_ports[address]:
                scan_finding.add_port(port)
                print(f"  {port}")
            result.add_finding(scan_finding)
        return result


def test_network(kube_client):
    try:
        kube_client.create_namespace(client.V1Namespace(
            metadata=client.V1ObjectMeta(name='astronomer-scan-test')))
    except Exception as e:
        if not 'already exists' in str(e):
            raise e
        print("namespace astronomer-scan-test already exists, proceeding")
    network_assessment = KubernetesNetworkChecker()
    network_assessment.collect_scan_targets()
    logging.info(f"Collected {len(network_assessment.targets)} scan targets")
    scan_result = network_assessment.scan_all_targets()
    allow_list = ["pod/coredns-",
                  "service/kube-dns",
                  "service/kubernetes",
                  "service/astronomer-nginx",
                  "pod/astronomer-nginx",
                  "service/astronomer-prometheus-node-exporter",
                  "pod/astronomer-prometheus-node-exporter"]
    for finding in scan_result.findings:
        allowed = False
        for allow in allow_list:
            if allow in finding.name:
                allowed = True
        if not allowed:
            raise Exception(f"Found {finding.name} has ports {finding.ports} open")
