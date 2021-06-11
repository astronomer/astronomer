# This should match the major.minor version list in .circleci/generate_circleci_config.py
supported_k8s_versions = [f"1.{x}.0" for x in range(16, 21)]
