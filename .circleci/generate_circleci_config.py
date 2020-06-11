#!/usr/bin/env python3
"""
This script is used to create the circle config file
so that we can stay DRY.
"""

import os
from jinja2 import Template

# When adding a new version, look up the most
# recent patch version on Dockerhub
KUBE_VERSIONS = ['1.14.10',
        '1.15.11',
        '1.16.9',
        '1.17.5',
        '1.18.2']

def main():
    """ Render the Jinja2 template file
    """
    circle_directory = os.path.dirname(os.path.realpath(__file__))
    config_template_path = os.path.join(circle_directory, "config.yml.j2")
    config_path = os.path.join(circle_directory, "config.yml")

    with open(config_template_path, "r") as circle_ci_config_template:
        templated_file_content = circle_ci_config_template.read()
    template = Template(templated_file_content)
    config = template.render(
            kube_versions=KUBE_VERSIONS
            )
    warning_header = "# Warning: automatically generated file\n" + \
            "# Please edit config.yml.j2, and use the script generate_circleci_config.py\n"
    with open(config_path, "w") as circle_ci_config_file:
        circle_ci_config_file.write(warning_header)
        circle_ci_config_file.write(config)


if __name__ == "__main__":
    main()
