Docker Images for the Astronomer Platform
===

Docker images for deploying and running the Astronomer Platform.  The images are currently available on [DockerHub](https://hub.docker.com/u/astronomerio/).

Full documentation for using the images can be found [here](https://astronomerio.github.io/astronomer/).

# Goals

- This repo contains our Dockerfiles that pull in and install the corresponding tagged releases.
- Develop and tag matching release numbers in their corresponding repos for each major platform release. Eg: event-router@1.0.0, asds@1.0.0, houston@1.0.0, galaxy@1.0.0 and so on.
- Include a directory of docker-compose files that pull together and launch different flavors of the platform, using the images produced by the Dockerfiles. These are for getting up and running with the platform quickly and easily, focus on UX here.
- A Makefile to make it simple to rebuild the entire platform for new releases, as well as some extra dev commands.
- Platform-wide documentation.

# Contribute

- Source Code: https://github.com/astronomerio/astronomer
- Issue Tracker: https://github.com/astronomerio/astronomer

# License

The project is licensed under the Apache 2 license. For more information on the licenses for each of the individual Astronomer Platform components packaged in the images, please refer to the respective [Astronomer Platform documentation for each component](https://astronomerio.github.io/astronomer/).  

