import subprocess
import json
import time
import sys


def check_all_pods_running():
    result = subprocess.run(["kubectl", "get", "pods", "-n", "astronomer", "-o", "json"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error getting pods: {result.stderr}")
        return False
    pods = json.loads(result.stdout)
    all_running = True
    for pod in pods["items"]:
        pod_name = pod["metadata"]["name"]
        namespace = pod["metadata"]["namespace"]

        phase = pod["status"]["phase"]
        is_valid_state = phase in ["Running", "Completed"]

        container_statuses = pod["status"].get("containerStatuses", [])
        all_containers_ready = all(status.get("ready", False) for status in container_statuses)

        status_msg = f"Pod: {namespace}/{pod_name} - Phase: {phase}"
        if not is_valid_state or (phase == "Running" and not all_containers_ready):
            all_running = False
            print(f"{status_msg} - Not all containers ready")
        else:
            print(f"{status_msg}")
    return all_running


def wait_for_pods(timeout_seconds=300):
    print(f"Waiting up to {timeout_seconds} seconds for all pods to be in Running state...")
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if check_all_pods_running():
            print("All pods are in Running state.")
            return True

        print("\nNot all pods are ready yet. Waiting 10 seconds before checking again...")
        time.sleep(10)
    print(f"\nTimeout after {timeout_seconds} seconds. Not all pods are running.")
    return False


if __name__ == "__main__":
    success = wait_for_pods(timeout_seconds=300)
    if not success:
        sys.exit(1)
