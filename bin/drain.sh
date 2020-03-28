set -xe
kubectl uncordon kind-worker
kubectl cordon kind-worker2
kubectl drain --force --delete-local-data --ignore-daemonsets kind-worker2
