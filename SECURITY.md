# Astronomer Platform Security Notes

* No Dockerfile HEALTHCHECK — We don't add HEALTHCHECK lines to our Dockerfiles since we declare healthchecks using Kubernetes. Dockerfile HEALTHCHECK lines don't have any effect in Kubernetes-land. All of our long-running services should have a healthcheck declared in their manifests. [Houston](https://github.com/astronomer/astronomer/blob/master/charts/astronomer/templates/houston/houston-deployment.yaml#L81-L94), for example.
