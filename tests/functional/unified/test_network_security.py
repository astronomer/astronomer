"""
Network Security Testing Module for Kubernetes Clusters

This module provides functionality to perform network security assessments on Kubernetes
clusters by scanning for open ports on pods and services. It uses nmap to scan network
targets and validates that only allowed services and pods have open ports.

The testing process:
1. Discovers all pods and services in the cluster
2. Creates a temporary scanning pod with nmap
3. Scans all discovered targets for open ports
4. Validates results against an allowlist of expected open ports
"""

import logging
import sys
import xml.etree.ElementTree as xml_parser
from contextlib import contextmanager
from os import getenv
from time import sleep, strftime, time

import testinfra
from kubernetes import client, config

from tests.utils.k8s import KUBECONFIG_UNIFIED

# Configure logging based on DEBUG environment variable
if getenv("DEBUG"):
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
else:
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)


class ScanFinding:
    """
    Represents a network security finding from a port scan.

    A finding contains information about a discovered network target
    that has open ports, including the target's name, IP address,
    and list of open ports.
    """

    def __init__(self, name="", ip_address="", ports=None):
        """
        Initialize a new scan finding.

        Args:
            name (str): Human-readable name of the target (e.g., "pod/nginx-app")
            ip_address (str): IP address of the scanned target
            ports (list): List of open port numbers, defaults to empty list
        """
        if ports is None:
            ports = []
        self.name = name
        self.ip_address = ip_address
        self.ports = ports

    def add_port(self, port):
        """
        Add a port to the finding if it's not already present.

        Args:
            port (int): Port number to add to the finding
        """
        if port not in self.ports:
            self.ports.append(port)


class ScanResult:
    """
    Container for multiple scan findings from a network security assessment.

    Manages a collection of ScanFinding objects representing all discovered
    network security issues during a scan operation.
    """

    def __init__(self, findings=None):
        """
        Initialize a new scan result container.

        Args:
            findings (list): List of ScanFinding objects, defaults to empty list
        """
        if findings is None:
            findings = []
        self.findings = findings

    def add_finding(self, finding):
        """
        Add a new finding to the scan results.

        Args:
            finding (ScanFinding): The finding to add to the results
        """
        self.findings.append(finding)

    def remove_finding(self, finding):
        """
        Remove a finding from the scan results.

        Args:
            finding (ScanFinding): The finding to remove from the results
        """
        self.findings.remove(finding)


class ScanTarget:
    """
    Represents a Kubernetes resource that should be scanned for open ports.

    A scan target contains metadata about a Kubernetes pod or service including
    its network configuration and expected ports.
    """

    def __init__(self, name, ip_address, _type, ports=None, namespace=None):
        """
        Initialize a new scan target.

        Args:
            name (str): Name of the Kubernetes resource
            ip_address (str): IP address to scan
            _type (str): Type of resource, must be 'pod' or 'service'
            ports (list): List of expected port numbers, defaults to empty list
            namespace (str): Kubernetes namespace containing the resource

        Raises:
            AssertionError: If parameters don't meet type/value requirements
        """
        if ports is None:
            ports = []
        self.name = name
        self.ip_address = ip_address
        assert isinstance(self.ip_address, str), f"Expected to find str, but found: {type(ip_address)}"
        self._type = _type
        assert self._type in [
            "pod",
            "service",
        ], f"Expected to find 'pod' or 'service', but found {self._type}"
        self.ports = ports
        for port in self.ports:
            assert isinstance(port, int), f"Expected to find int, but found: {type(port)}"
        self.namespace = namespace
        assert isinstance(self.namespace, str), f"Expected to find str, but found: {type(self.namespace)}"


class KubernetesNetworkChecker:
    """
    Main class for performing network security assessments on Kubernetes clusters.

    This class discovers pods and services in a Kubernetes cluster, creates a temporary
    scanning pod with nmap, and performs network scans to identify open ports that
    may represent security vulnerabilities.
    """

    def __init__(self):
        """
        Initialize the network checker with Kubernetes API client.

        Loads the kubeconfig and sets up the Kubernetes API client for
        discovering cluster resources.
        """
        config.load_kube_config(config_file=str(KUBECONFIG_UNIFIED))
        self.targets = []
        self.v1 = client.CoreV1Api()

    def collect_scan_targets(self):
        """
        Discover all pods and services in the cluster to create scan targets.

        Iterates through all namespaces to find pods and services with exposed ports.
        Only resources with defined ports are added as scan targets.

        Populates self.targets with ScanTarget objects for discovered resources.
        """
        logging.info("Iterating through all pods")

        # Collect pod targets
        pods = self.v1.list_pod_for_all_namespaces(watch=False)
        for pod in pods.items:
            ip = pod.status.pod_ip
            if not ip:
                continue  # Skip pods without IP addresses

            name = pod.metadata.name
            namespace = pod.metadata.namespace
            ports = []

            # Extract container ports from pod specification
            for container in pod.spec.containers:
                if not container.ports:
                    continue
                ports.extend(port.container_port for port in container.ports)

            target = ScanTarget(name, ip, "pod", ports=ports, namespace=namespace)
            if ports:  # Only add targets that have ports to scan
                self.targets.append(target)

        # Collect service targets
        services = self.v1.list_service_for_all_namespaces(watch=False)
        for service in services.items:
            ip = service.spec.cluster_ip
            name = service.metadata.name
            namespace = service.metadata.namespace
            ports = [port.port for port in service.spec.ports]

            target = ScanTarget(name, ip, "service", ports=ports, namespace=namespace)
            if ports:  # Only add targets that have ports to scan
                self.targets.append(target)

    @contextmanager
    def _scanning_pod(self):
        """
        Context manager that creates and manages a temporary scanning pod.

        Creates a Kubernetes pod with nmap installed to perform network scans
        from within the cluster. The pod is automatically cleaned up when
        the context exits.

        Yields:
            testinfra.Host: Test fixture for executing commands in the scanning pod

        Raises:
            Exception: If the pod fails to start within the timeout period
        """
        namespace = "astronomer-scan-test"
        pod_name = f"network-scanner-{strftime('%s')}"

        # Configure the scanning pod with Alpine Linux and sleep command
        v1container = client.V1Container(name="scanner")
        v1container.command = ["sleep", "300"]  # Keep pod alive for 5 minutes
        v1container.image = "alpine"
        v1podspec = client.V1PodSpec(containers=[v1container])
        v1objectmeta = client.V1ObjectMeta(name=pod_name)
        v1pod = client.V1Pod(spec=v1podspec, metadata=v1objectmeta)

        logging.info(f"Creating {pod_name} pod in namespace {namespace}")
        pod = self.v1.create_namespaced_pod(namespace, v1pod)
        sleep(2)  # Allow pod to transition to 'Pending' state

        try:
            # Wait for pod to become ready with timeout
            timeout = 120
            start = time()
            while True:
                if time() - start > timeout:
                    raise Exception("Timed out waiting for pod to start")
                sleep(1)

                check_pod = self.v1.read_namespaced_pod(pod.metadata.name, namespace)
                if check_pod.status.container_statuses[0].ready:
                    logging.info("network-scanner is ready")
                    break

            # Create testinfra fixture for executing commands in the pod
            test_fixture = testinfra.get_host(
                f"kubectl://{pod.metadata.name}?" + f"container={v1container.name}&namespace={namespace}",
                kubeconfig=str(KUBECONFIG_UNIFIED),
            )

            # Install nmap in the scanning pod
            logging.info("Installing nmap into network-scanner")
            test_fixture.check_output("apk add nmap")
            test_fixture.exists("nmap")

            yield test_fixture

        finally:
            # Clean up the scanning pod
            logging.info(f"Cleaning up network-scanner pod from namespace {namespace}")
            self.v1.delete_namespaced_pod(v1pod.metadata.name, namespace)

    def _collect_scan_parameters(self) -> tuple[list[int], set[str]]:
        """
        Extract unique ports and IP addresses from all scan targets.

        Returns:
            tuple: (all_ports, all_ips) where all_ports is a list of unique port numbers
                  and all_ips is a set of unique IP addresses to scan
        """
        all_ports = set()
        for target in self.targets:
            for port in target.ports:
                all_ports.add(port)
        all_ports_list = list(all_ports)
        all_ips = {target.ip_address for target in self.targets}

        return all_ports_list, all_ips

    def _execute_nmap_scan(self, all_ports: list[int], all_ips: set[str]) -> str:
        """
        Execute nmap scan against target IPs and ports using scanning pod.

        Args:
            all_ports: List of port numbers to scan
            all_ips: Set of IP addresses to scan

        Returns:
            str: Raw XML output from nmap scan
        """
        with self._scanning_pod() as scanner:
            scanner.check_output("whoami")  # Verify scanner pod is working

            # Build nmap command with optimized settings for cluster scanning
            ports_string = ",".join([str(port) for port in all_ports])
            addresses_string = " ".join(all_ips)

            logging.info("Executing scan...")
            command = (
                "nmap --max-retries 2 -T5 --max-rtt-timeout 100ms "  # Fast scan settings
                + "-Pn -oX /scan-results.xml "  # Skip ping, output XML
                + f"-p{ports_string} {addresses_string}"
            )
            logging.info(f"running command: {command}")

            # Execute the scan and measure duration
            start = time()
            scanner.check_output(command)
            duration = time() - start
            logging.info(f"Command took {duration} seconds")

            # Retrieve scan results
            return scanner.check_output("cat /scan-results.xml")

    def _parse_nmap_results(self, xml_result: str) -> dict[str, list[int]]:
        """
        Parse nmap XML output to extract open ports by IP address.

        Args:
            xml_result: Raw XML output from nmap scan

        Returns:
            dict: Mapping of IP addresses to lists of open port numbers
        """
        root = xml_parser.fromstring(xml_result)
        open_ports = {}

        for child in root:
            if child.tag != "host":
                continue

            ip_address = None

            for grandchild in child:
                # Extract IP address from the host entry
                if grandchild.tag == "address":
                    ip_address = grandchild.attrib["addr"]

                # Process port scan results
                elif grandchild.tag == "ports":
                    for port in grandchild:
                        is_open = False

                        # Check if port is in 'open' state
                        for state in port:
                            if state.tag != "state":
                                continue
                            is_open = state.attrib["state"] == "open"

                        # Record open ports by IP address
                        if is_open and ip_address:
                            if ip_address not in open_ports:
                                open_ports[ip_address] = []
                            open_ports[ip_address].append(int(port.attrib["portid"]))

        return open_ports

    def _create_scan_findings(self, open_ports: dict[str, list[int]]) -> ScanResult:
        """
        Convert open ports data into ScanFinding objects.

        Args:
            open_ports: Mapping of IP addresses to lists of open port numbers

        Returns:
            ScanResult: Object containing all findings from the network scan
        """
        result = ScanResult()

        for address, ports in open_ports.items():
            if not ports:
                continue

            scan_finding = ScanFinding()
            scan_finding.ip_address = address

            # Match IP address to target name for better reporting
            for target in self.targets:
                if target.ip_address == address:
                    scan_finding.name = f"{target._type}/{target.name}"
                    print(f"{target._type} {target.name} ({address}):")
                    break

            # Add all open ports to the finding
            for port in ports:
                scan_finding.add_port(port)
                print(f"  {port}")

            result.add_finding(scan_finding)

        return result

    def scan_all_targets(self) -> ScanResult:
        """
        Perform network scans on all discovered targets using nmap.

        Creates a temporary scanning pod and uses nmap to scan all target IP addresses
        for open ports. Parses the nmap XML output to identify which ports are open
        on each target.

        Returns:
            ScanResult: Object containing all findings from the network scan
        """
        # Collect all unique ports and IP addresses from targets
        all_ports, all_ips = self._collect_scan_parameters()

        # Note: nmap scans all ports on all hosts since it doesn't support per-target port lists
        xml_result = self._execute_nmap_scan(all_ports, all_ips)

        # Parse nmap XML output to extract open ports
        open_ports = self._parse_nmap_results(xml_result)

        # Create scan findings from open ports
        return self._create_scan_findings(open_ports)


def test_network_security(k8s_core_v1_client):
    """
    Main test function that performs network security validation on a Kubernetes cluster.

    This function orchestrates the complete network security assessment process:
    1. Creates a test namespace for scanning operations
    2. Discovers all pods and services in the cluster
    3. Performs network scans to identify open ports
    4. Validates that only allowed services have open ports

    Args:
        k8s_core_v1_client: Kubernetes CoreV1Api client for cluster operations

    Raises:
        Exception: If any non-allowlisted services are found with open ports
    """
    # Create namespace for scanning operations (ignore if already exists)
    try:
        k8s_core_v1_client.create_namespace(client.V1Namespace(metadata=client.V1ObjectMeta(name="astronomer-scan-test")))
    except Exception as e:
        if "already exists" not in str(e):
            raise e
        print("namespace astronomer-scan-test already exists, proceeding")

    # Perform network security assessment
    network_assessment = KubernetesNetworkChecker()
    network_assessment.collect_scan_targets()
    logging.info(f"Collected {len(network_assessment.targets)} scan targets")

    scan_result = network_assessment.scan_all_targets()

    # Define allowlist of services that are expected to have open ports
    # These are core Kubernetes services and expected application components
    allow_list = [
        "pod/coredns-",  # DNS resolution pods
        "service/kube-dns",  # DNS service
        "service/kubernetes",  # Kubernetes API server
        "service/astronomer-nginx",  # Astronomer ingress service
        "pod/astronomer-nginx",  # Astronomer ingress pods
    ]

    # Validate scan results - fail if any non-allowlisted services have open ports
    for finding in scan_result.findings:
        allowed = any(allow in finding.name for allow in allow_list)
        if not allowed:
            raise Exception(f"Found {finding.name} has ports {finding.ports} open")
