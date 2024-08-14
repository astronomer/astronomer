
****cre_astro_gather_logs Script****
====================================

This script will export pod logs, events, helm values, node status, secrets, rs, Ingres, jobs, etc. which are required chiefly for troubleshooting purposes.

Also, it will describe the output of all the nodes & the status of pods in a bad state.

We have to make sure to add the below parameters in the script. The script is interactive and would ask the same

1.) Astronomer namespace (Astronomer Namespace to collect logs)

2.) DIR (local directory to export the logs)

3.) BASEDOMAIN (I had a test cluster with the URL https://app.nandlal51.astro-cre.comthen my base domain isnandlal51.astro-cre.com

~~~
export ASTRONOMER_NAMESPACE=
export DIR=
export BASEDOMAIN=
~~~

Usage: Just run the shell script as below and you will get the required log files.

Kindly make sure your script is in Unix format and executable:

~~~
dos2unix *.sh 
chmod 755 *.sh
~~~

Expected output:

![image](https://user-images.githubusercontent.com/33649510/191579495-68d37f5c-74f9-4372-a2df-2be9e8768ba9.png)


![image](https://user-images.githubusercontent.com/33649510/190877503-5ada590a-75cf-41bd-93e0-7b6d59bb7f2c.png)

![image](https://user-images.githubusercontent.com/33649510/190877507-43b1fbc5-b324-46ba-8c5d-3938778af85f.png)

![image](https://user-images.githubusercontent.com/33649510/190877494-200d7b26-2e78-439b-8e35-8c419aad3858.png)

![image](https://user-images.githubusercontent.com/33649510/191654823-4251832c-6f6b-4589-adfb-5a77baa6f3fb.png)









Here is the expected Script Output:


```
[root@DESKTOP-JJ9MM59 Gather logs]# sh cre_astro_gather_logs.sh
Enter your Astronomer Namespace Name:
astronomer
Enter the path of directory where you want to keep your log files exported:
/tmp
If had a test cluster with the URL https://app.xyz.astro-cre.com then my base domain is xyz.astro-cre.com
what is your basedomain:
nandlal51.astro-cre.com
====> Here is the list of Namespaces found:
NAME                                         STATUS   AGE
astronomer                                   Active   16d
astronomer-extraterrestrial-meteorite-6103   Active   2d
astronomer-transparent-terminator-3163       Active   102m
cluster-autoscaler                           Active   16d
default                                      Active   16d
kube-node-lease                              Active   16d
kube-public                                  Active   16d
kube-system                                  Active   16d
====> You have specied astronomer as a namespace where all the core Astronomer platform pods are running.Please make sure it's correctly specified.
====> Your astronomer release name is astronomer.
====> The path where logs would be stored is /tmp/astro_logs.
====> Your Base Domain is nandlal51.astro-cre.com.This means you should access your Astronomer UI at https://app.nandlal51.astro-cre.com
====> cleaning any older /tmp/astro_logs directory to avoid script failure
====> Creating log file directory /tmp/astro_logs.
creating namespace astronomer Directory
creating namespace astronomer-extraterrestrial-meteorite-6103 Directory
creating namespace astronomer-transparent-terminator-3163 Directory
creating namespace cluster-autoscaler Directory
creating namespace default Directory
creating namespace kube-node-lease Directory
creating namespace kube-public Directory
creating namespace kube-system Directory
======================Gathering Describe output of Bad state pod======================
^C
[root@DESKTOP-JJ9MM59 Gather logs]# sh cre_astro_gather_logs.sh >> new.log
^C
[root@DESKTOP-JJ9MM59 Gather logs]# sh cre_astro_gather_logs.sh
Enter your Astronomer Namespace Name:
astronomer
Enter the path of directory where you want to keep your log files exported:
/tmp
If had a test cluster with the URL https://app.xyz.astro-cre.com then my base domain is xyz.astro-cre.com
what is your basedomain:
nandlal51.astro-cre.com
====> Here is the list of Namespaces found:
NAME                                         STATUS   AGE
astronomer                                   Active   16d
astronomer-extraterrestrial-meteorite-6103   Active   2d
astronomer-transparent-terminator-3163       Active   103m
cluster-autoscaler                           Active   16d
default                                      Active   16d
kube-node-lease                              Active   16d
kube-public                                  Active   16d
kube-system                                  Active   16d
====> You have specied astronomer as a namespace where all the core Astronomer platform pods are running.Please make sure it's correctly specified.
====> Your astronomer release name is astronomer.
====> The path where logs would be stored is /tmp/astro_logs.
====> Your Base Domain is nandlal51.astro-cre.com.This means you should access your Astronomer UI at https://app.nandlal51.astro-cre.com
====> cleaning any older /tmp/astro_logs directory to avoid script failure
====> Creating log file directory /tmp/astro_logs.
creating namespace astronomer Directory
creating namespace astronomer-extraterrestrial-meteorite-6103 Directory
creating namespace astronomer-transparent-terminator-3163 Directory
creating namespace cluster-autoscaler Directory
creating namespace default Directory
creating namespace kube-node-lease Directory
creating namespace kube-public Directory
creating namespace kube-system Directory
======================Gathering Describe output of Bad state pod======================
extraterrestrial-meteorite-6103-triggerer-5f8fd74c55-cj67f pod is in bad state
Collecting Describe output of bad state pod extraterrestrial-meteorite-6103-triggerer-5f8fd74c55-cj67f in astronomer-extraterrestrial-meteorite-6103 Namespace
extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b pod is in bad state
Collecting Describe output of bad state pod extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b in astronomer-extraterrestrial-meteorite-6103 Namespace
No resources found in default namespace.
No resources found in kube-node-lease namespace.
No resources found in kube-public namespace.
======================Gathering logs of All the pods ======================
Starting to Collect log of the pod astronomer-alertmanager-0 in astronomer namespace
Collecting log of the container alertmanager in pod astronomer-alertmanager-0 in the astronomer namespace now
Starting to Collect log of the pod astronomer-astro-ui-5b44b44f4-rnq84 in astronomer namespace
Collecting log of the container astro-ui in pod astronomer-astro-ui-5b44b44f4-rnq84 in the astronomer namespace now
Starting to Collect log of the pod astronomer-astro-ui-5b44b44f4-vnfmc in astronomer namespace
Collecting log of the container astro-ui in pod astronomer-astro-ui-5b44b44f4-vnfmc in the astronomer namespace now
Starting to Collect log of the pod astronomer-cli-install-9c6dc84f7-sf8vp in astronomer namespace
Collecting log of the container cli-install in pod astronomer-cli-install-9c6dc84f7-sf8vp in the astronomer namespace now
Starting to Collect log of the pod astronomer-commander-57559fc99f-dfc5b in astronomer namespace
Collecting log of the container commander in pod astronomer-commander-57559fc99f-dfc5b in the astronomer namespace now
Starting to Collect log of the pod astronomer-commander-57559fc99f-vkxjb in astronomer namespace
Collecting log of the container commander in pod astronomer-commander-57559fc99f-vkxjb in the astronomer namespace now
Starting to Collect log of the pod astronomer-config-syncer-27727698-r4w4k in astronomer namespace
Collecting log of the container config-syncer in pod astronomer-config-syncer-27727698-r4w4k in the astronomer namespace now
Starting to Collect log of the pod astronomer-config-syncer-27729138-sppns in astronomer namespace
Collecting log of the container config-syncer in pod astronomer-config-syncer-27729138-sppns in the astronomer namespace now
Starting to Collect log of the pod astronomer-elasticsearch-client-6f8f4f5897-2x85r in astronomer namespace
Collecting log of the container es-client in pod astronomer-elasticsearch-client-6f8f4f5897-2x85r in the astronomer namespace now
Starting to Collect log of the pod astronomer-elasticsearch-client-6f8f4f5897-gzgjr in astronomer namespace
Collecting log of the container es-client in pod astronomer-elasticsearch-client-6f8f4f5897-gzgjr in the astronomer namespace now
Starting to Collect log of the pod astronomer-elasticsearch-curator-27727260-nffh7 in astronomer namespace
Collecting log of the container curator in pod astronomer-elasticsearch-curator-27727260-nffh7 in the astronomer namespace now
Starting to Collect log of the pod astronomer-elasticsearch-curator-27728700-t69hz in astronomer namespace
Collecting log of the container curator in pod astronomer-elasticsearch-curator-27728700-t69hz in the astronomer namespace now
Starting to Collect log of the pod astronomer-elasticsearch-curator-27730140-q4nfm in astronomer namespace
Collecting log of the container curator in pod astronomer-elasticsearch-curator-27730140-q4nfm in the astronomer namespace now
Starting to Collect log of the pod astronomer-elasticsearch-data-0 in astronomer namespace
Collecting log of the container es-data in pod astronomer-elasticsearch-data-0 in the astronomer namespace now
Starting to Collect log of the pod astronomer-elasticsearch-data-1 in astronomer namespace
Collecting log of the container es-data in pod astronomer-elasticsearch-data-1 in the astronomer namespace now
Starting to Collect log of the pod astronomer-elasticsearch-exporter-8647676d-7dpqp in astronomer namespace
Collecting log of the container metrics-exporter in pod astronomer-elasticsearch-exporter-8647676d-7dpqp in the astronomer namespace now
Starting to Collect log of the pod astronomer-elasticsearch-master-0 in astronomer namespace
Collecting log of the container es-master in pod astronomer-elasticsearch-master-0 in the astronomer namespace now
Starting to Collect log of the pod astronomer-elasticsearch-master-1 in astronomer namespace
Collecting log of the container es-master in pod astronomer-elasticsearch-master-1 in the astronomer namespace now
Starting to Collect log of the pod astronomer-elasticsearch-master-2 in astronomer namespace
Collecting log of the container es-master in pod astronomer-elasticsearch-master-2 in the astronomer namespace now
Starting to Collect log of the pod astronomer-elasticsearch-nginx-859958bd58-vb7g7 in astronomer namespace
Collecting log of the container nginx in pod astronomer-elasticsearch-nginx-859958bd58-vb7g7 in the astronomer namespace now
Starting to Collect log of the pod astronomer-grafana-957c66f47-bvwjz in astronomer namespace
Collecting log of the container grafana in pod astronomer-grafana-957c66f47-bvwjz in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-cf67c758-4txb6 in astronomer namespace
Collecting log of the container houston in pod astronomer-houston-cf67c758-4txb6 in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-cf67c758-nkxsg in astronomer namespace
Collecting log of the container houston in pod astronomer-houston-cf67c758-nkxsg in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-cleanup-deployments-27727200-v49t2 in astronomer namespace
Collecting log of the container cleanup in pod astronomer-houston-cleanup-deployments-27727200-v49t2 in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-cleanup-deployments-27728640-2q6wl in astronomer namespace
Collecting log of the container cleanup in pod astronomer-houston-cleanup-deployments-27728640-2q6wl in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-cleanup-deployments-27730080-72sxq in astronomer namespace
Collecting log of the container cleanup in pod astronomer-houston-cleanup-deployments-27730080-72sxq in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-update-airflow-check-27730197-j28qp in astronomer namespace
Collecting log of the container update-check in pod astronomer-houston-update-airflow-check-27730197-j28qp in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-update-airflow-check-27730257-wwb4f in astronomer namespace
Collecting log of the container update-check in pod astronomer-houston-update-airflow-check-27730257-wwb4f in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-update-airflow-check-27730317-dv47f in astronomer namespace
Collecting log of the container update-check in pod astronomer-houston-update-airflow-check-27730317-dv47f in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-update-check-27727200-vpwn6 in astronomer namespace
Collecting log of the container update-check in pod astronomer-houston-update-check-27727200-vpwn6 in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-update-check-27728640-mnrmq in astronomer namespace
Collecting log of the container update-check in pod astronomer-houston-update-check-27728640-mnrmq in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-update-check-27730080-hnb5c in astronomer namespace
Collecting log of the container update-check in pod astronomer-houston-update-check-27730080-hnb5c in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-update-runtime-check-27727243-lkpkc in astronomer namespace
Collecting log of the container update-check in pod astronomer-houston-update-runtime-check-27727243-lkpkc in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-update-runtime-check-27728683-dsppq in astronomer namespace
Collecting log of the container update-check in pod astronomer-houston-update-runtime-check-27728683-dsppq in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-update-runtime-check-27730123-55w6l in astronomer namespace
Collecting log of the container update-check in pod astronomer-houston-update-runtime-check-27730123-55w6l in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-worker-f68cb689b-n8tqs in astronomer namespace
Collecting log of the container houston in pod astronomer-houston-worker-f68cb689b-n8tqs in the astronomer namespace now
Starting to Collect log of the pod astronomer-houston-worker-f68cb689b-w74lb in astronomer namespace
Collecting log of the container houston in pod astronomer-houston-worker-f68cb689b-w74lb in the astronomer namespace now
Starting to Collect log of the pod astronomer-kibana-5c49d7fd5f-rwsbp in astronomer namespace
Collecting log of the container kibana in pod astronomer-kibana-5c49d7fd5f-rwsbp in the astronomer namespace now
Starting to Collect log of the pod astronomer-kube-state-7fcbd4fb88-cjxf8 in astronomer namespace
Collecting log of the container kube-state in pod astronomer-kube-state-7fcbd4fb88-cjxf8 in the astronomer namespace now
Starting to Collect log of the pod astronomer-nats-0 in astronomer namespace
Collecting log of the container metrics in pod astronomer-nats-0 in the astronomer namespace now
Collecting log of the container nats in pod astronomer-nats-0 in the astronomer namespace now
Starting to Collect log of the pod astronomer-nats-1 in astronomer namespace
Collecting log of the container metrics in pod astronomer-nats-1 in the astronomer namespace now
Collecting log of the container nats in pod astronomer-nats-1 in the astronomer namespace now
Starting to Collect log of the pod astronomer-nats-2 in astronomer namespace
Collecting log of the container metrics in pod astronomer-nats-2 in the astronomer namespace now
Collecting log of the container nats in pod astronomer-nats-2 in the astronomer namespace now
Starting to Collect log of the pod astronomer-nginx-default-backend-864d4468b8-2tggh in astronomer namespace
Collecting log of the container default-backend in pod astronomer-nginx-default-backend-864d4468b8-2tggh in the astronomer namespace now
Starting to Collect log of the pod astronomer-nginx-default-backend-864d4468b8-bhl6b in astronomer namespace
Collecting log of the container default-backend in pod astronomer-nginx-default-backend-864d4468b8-bhl6b in the astronomer namespace now
Starting to Collect log of the pod astronomer-nginx-df4b74944-4ktlc in astronomer namespace
Collecting log of the container nginx in pod astronomer-nginx-df4b74944-4ktlc in the astronomer namespace now
Starting to Collect log of the pod astronomer-nginx-df4b74944-4vqfv in astronomer namespace
Collecting log of the container nginx in pod astronomer-nginx-df4b74944-4vqfv in the astronomer namespace now
Starting to Collect log of the pod astronomer-prometheus-0 in astronomer namespace
Collecting log of the container configmap-reloader in pod astronomer-prometheus-0 in the astronomer namespace now
Collecting log of the container prometheus in pod astronomer-prometheus-0 in the astronomer namespace now
Starting to Collect log of the pod astronomer-prometheus-node-exporter-2g5mz in astronomer namespace
Collecting log of the container node-exporter in pod astronomer-prometheus-node-exporter-2g5mz in the astronomer namespace now
Starting to Collect log of the pod astronomer-prometheus-node-exporter-49bgn in astronomer namespace
Collecting log of the container node-exporter in pod astronomer-prometheus-node-exporter-49bgn in the astronomer namespace now
Starting to Collect log of the pod astronomer-prometheus-node-exporter-5ck9d in astronomer namespace
Collecting log of the container node-exporter in pod astronomer-prometheus-node-exporter-5ck9d in the astronomer namespace now
Starting to Collect log of the pod astronomer-prometheus-node-exporter-7crxk in astronomer namespace
Collecting log of the container node-exporter in pod astronomer-prometheus-node-exporter-7crxk in the astronomer namespace now
Starting to Collect log of the pod astronomer-prometheus-node-exporter-dxr97 in astronomer namespace
Collecting log of the container node-exporter in pod astronomer-prometheus-node-exporter-dxr97 in the astronomer namespace now
Starting to Collect log of the pod astronomer-prometheus-node-exporter-g22qd in astronomer namespace
Collecting log of the container node-exporter in pod astronomer-prometheus-node-exporter-g22qd in the astronomer namespace now
Starting to Collect log of the pod astronomer-prometheus-node-exporter-hw4tv in astronomer namespace
Collecting log of the container node-exporter in pod astronomer-prometheus-node-exporter-hw4tv in the astronomer namespace now
Starting to Collect log of the pod astronomer-prometheus-node-exporter-ldj66 in astronomer namespace
Collecting log of the container node-exporter in pod astronomer-prometheus-node-exporter-ldj66 in the astronomer namespace now
Starting to Collect log of the pod astronomer-prometheus-node-exporter-lnfhm in astronomer namespace
Collecting log of the container node-exporter in pod astronomer-prometheus-node-exporter-lnfhm in the astronomer namespace now
Starting to Collect log of the pod astronomer-prometheus-node-exporter-x8b2g in astronomer namespace
Collecting log of the container node-exporter in pod astronomer-prometheus-node-exporter-x8b2g in the astronomer namespace now
Starting to Collect log of the pod astronomer-registry-0 in astronomer namespace
Collecting log of the container registry in pod astronomer-registry-0 in the astronomer namespace now
Starting to Collect log of the pod astronomer-stan-0 in astronomer namespace
Collecting log of the container metrics in pod astronomer-stan-0 in the astronomer namespace now
Collecting log of the container stan in pod astronomer-stan-0 in the astronomer namespace now
Starting to Collect log of the pod astronomer-stan-1 in astronomer namespace
Collecting log of the container metrics in pod astronomer-stan-1 in the astronomer namespace now
Collecting log of the container stan in pod astronomer-stan-1 in the astronomer namespace now
Starting to Collect log of the pod astronomer-stan-2 in astronomer namespace
Collecting log of the container metrics in pod astronomer-stan-2 in the astronomer namespace now
Collecting log of the container stan in pod astronomer-stan-2 in the astronomer namespace now
Starting to Collect log of the pod extraterrestrial-meteorite-6103-cleanup-27730326-xzq87 in astronomer-extraterrestrial-meteorite-6103 namespace
Collecting log of the container airflow-cleanup-pods in pod extraterrestrial-meteorite-6103-cleanup-27730326-xzq87 in the astronomer-extraterrestrial-meteorite-6103 namespace now
Starting to Collect log of the pod extraterrestrial-meteorite-6103-flower-b58f9cc5d-mp86c in astronomer-extraterrestrial-meteorite-6103 namespace
Collecting log of the container flower in pod extraterrestrial-meteorite-6103-flower-b58f9cc5d-mp86c in the astronomer-extraterrestrial-meteorite-6103 namespace now
Starting to Collect log of the pod extraterrestrial-meteorite-6103-pgbouncer-778666fbf4-5f4ls in astronomer-extraterrestrial-meteorite-6103 namespace
Collecting log of the container metrics-exporter in pod extraterrestrial-meteorite-6103-pgbouncer-778666fbf4-5f4ls in the astronomer-extraterrestrial-meteorite-6103 namespace now
Collecting log of the container pgbouncer in pod extraterrestrial-meteorite-6103-pgbouncer-778666fbf4-5f4ls in the astronomer-extraterrestrial-meteorite-6103 namespace now
Starting to Collect log of the pod extraterrestrial-meteorite-6103-redis-0 in astronomer-extraterrestrial-meteorite-6103 namespace
Collecting log of the container redis in pod extraterrestrial-meteorite-6103-redis-0 in the astronomer-extraterrestrial-meteorite-6103 namespace now
Starting to Collect log of the pod extraterrestrial-meteorite-6103-scheduler-d6f644c7d-ffrzk in astronomer-extraterrestrial-meteorite-6103 namespace
Collecting log of the container scheduler in pod extraterrestrial-meteorite-6103-scheduler-d6f644c7d-ffrzk in the astronomer-extraterrestrial-meteorite-6103 namespace now
Collecting log of the container scheduler-log-groomer in pod extraterrestrial-meteorite-6103-scheduler-d6f644c7d-ffrzk in the astronomer-extraterrestrial-meteorite-6103 namespace now
Collecting log of the container sidecar-log-consumer in pod extraterrestrial-meteorite-6103-scheduler-d6f644c7d-ffrzk in the astronomer-extraterrestrial-meteorite-6103 namespace now
Starting to Collect log of the pod extraterrestrial-meteorite-6103-scheduler-d6f644c7d-tvs6n in astronomer-extraterrestrial-meteorite-6103 namespace
Collecting log of the container scheduler in pod extraterrestrial-meteorite-6103-scheduler-d6f644c7d-tvs6n in the astronomer-extraterrestrial-meteorite-6103 namespace now
Collecting log of the container scheduler-log-groomer in pod extraterrestrial-meteorite-6103-scheduler-d6f644c7d-tvs6n in the astronomer-extraterrestrial-meteorite-6103 namespace now
Collecting log of the container sidecar-log-consumer in pod extraterrestrial-meteorite-6103-scheduler-d6f644c7d-tvs6n in the astronomer-extraterrestrial-meteorite-6103 namespace now
Starting to Collect log of the pod extraterrestrial-meteorite-6103-statsd-78bfc6db4f-kqbfw in astronomer-extraterrestrial-meteorite-6103 namespace
Collecting log of the container statsd in pod extraterrestrial-meteorite-6103-statsd-78bfc6db4f-kqbfw in the astronomer-extraterrestrial-meteorite-6103 namespace now
Starting to Collect log of the pod extraterrestrial-meteorite-6103-triggerer-5f8fd74c55-cj67f in astronomer-extraterrestrial-meteorite-6103 namespace
Collecting log of the container sidecar-log-consumer in pod extraterrestrial-meteorite-6103-triggerer-5f8fd74c55-cj67f in the astronomer-extraterrestrial-meteorite-6103 namespace now
Collecting log of the container triggerer in pod extraterrestrial-meteorite-6103-triggerer-5f8fd74c55-cj67f in the astronomer-extraterrestrial-meteorite-6103 namespace now
Error from server (BadRequest): container "triggerer" in pod "extraterrestrial-meteorite-6103-triggerer-5f8fd74c55-cj67f" is waiting to start: trying and failing to pull image
Starting to Collect log of the pod extraterrestrial-meteorite-6103-triggerer-7fffd75596-s287g in astronomer-extraterrestrial-meteorite-6103 namespace
Collecting log of the container sidecar-log-consumer in pod extraterrestrial-meteorite-6103-triggerer-7fffd75596-s287g in the astronomer-extraterrestrial-meteorite-6103 namespace now
Collecting log of the container triggerer in pod extraterrestrial-meteorite-6103-triggerer-7fffd75596-s287g in the astronomer-extraterrestrial-meteorite-6103 namespace now
Starting to Collect log of the pod extraterrestrial-meteorite-6103-webserver-7869b4d57f-kpftf in astronomer-extraterrestrial-meteorite-6103 namespace
Collecting log of the container sidecar-log-consumer in pod extraterrestrial-meteorite-6103-webserver-7869b4d57f-kpftf in the astronomer-extraterrestrial-meteorite-6103 namespace now
Collecting log of the container webserver in pod extraterrestrial-meteorite-6103-webserver-7869b4d57f-kpftf in the astronomer-extraterrestrial-meteorite-6103 namespace now
Starting to Collect log of the pod extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b in astronomer-extraterrestrial-meteorite-6103 namespace
Collecting log of the container sidecar-log-consumer in pod extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b in the astronomer-extraterrestrial-meteorite-6103 namespace now
Error from server (BadRequest): container "sidecar-log-consumer" in pod "extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b" is waiting to start: PodInitializing
Collecting log of the container worker in pod extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b in the astronomer-extraterrestrial-meteorite-6103 namespace now
Error from server (BadRequest): container "worker" in pod "extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b" is waiting to start: PodInitializing
Starting to Collect log of the pod extraterrestrial-meteorite-6103-worker-77fdc7d6d7-rmvtg in astronomer-extraterrestrial-meteorite-6103 namespace
Collecting log of the container sidecar-log-consumer in pod extraterrestrial-meteorite-6103-worker-77fdc7d6d7-rmvtg in the astronomer-extraterrestrial-meteorite-6103 namespace now
Collecting log of the container worker in pod extraterrestrial-meteorite-6103-worker-77fdc7d6d7-rmvtg in the astronomer-extraterrestrial-meteorite-6103 namespace now
Starting to Collect log of the pod transparent-terminator-3163-cleanup-27730326-msrlz in astronomer-transparent-terminator-3163 namespace
Collecting log of the container airflow-cleanup-pods in pod transparent-terminator-3163-cleanup-27730326-msrlz in the astronomer-transparent-terminator-3163 namespace now
Starting to Collect log of the pod transparent-terminator-3163-flower-656699b5fb-2k78m in astronomer-transparent-terminator-3163 namespace
Collecting log of the container flower in pod transparent-terminator-3163-flower-656699b5fb-2k78m in the astronomer-transparent-terminator-3163 namespace now
Starting to Collect log of the pod transparent-terminator-3163-pgbouncer-6c94bc5b99-sgkvp in astronomer-transparent-terminator-3163 namespace
Collecting log of the container metrics-exporter in pod transparent-terminator-3163-pgbouncer-6c94bc5b99-sgkvp in the astronomer-transparent-terminator-3163 namespace now
Collecting log of the container pgbouncer in pod transparent-terminator-3163-pgbouncer-6c94bc5b99-sgkvp in the astronomer-transparent-terminator-3163 namespace now
Starting to Collect log of the pod transparent-terminator-3163-redis-0 in astronomer-transparent-terminator-3163 namespace
Collecting log of the container redis in pod transparent-terminator-3163-redis-0 in the astronomer-transparent-terminator-3163 namespace now
Starting to Collect log of the pod transparent-terminator-3163-scheduler-8b6858fdf-6zbqp in astronomer-transparent-terminator-3163 namespace
Collecting log of the container scheduler in pod transparent-terminator-3163-scheduler-8b6858fdf-6zbqp in the astronomer-transparent-terminator-3163 namespace now
Collecting log of the container scheduler-log-groomer in pod transparent-terminator-3163-scheduler-8b6858fdf-6zbqp in the astronomer-transparent-terminator-3163 namespace now
Collecting log of the container sidecar-log-consumer in pod transparent-terminator-3163-scheduler-8b6858fdf-6zbqp in the astronomer-transparent-terminator-3163 namespace now
Starting to Collect log of the pod transparent-terminator-3163-scheduler-8b6858fdf-bs6nf in astronomer-transparent-terminator-3163 namespace
Collecting log of the container scheduler in pod transparent-terminator-3163-scheduler-8b6858fdf-bs6nf in the astronomer-transparent-terminator-3163 namespace now
Collecting log of the container scheduler-log-groomer in pod transparent-terminator-3163-scheduler-8b6858fdf-bs6nf in the astronomer-transparent-terminator-3163 namespace now
Collecting log of the container sidecar-log-consumer in pod transparent-terminator-3163-scheduler-8b6858fdf-bs6nf in the astronomer-transparent-terminator-3163 namespace now
Starting to Collect log of the pod transparent-terminator-3163-statsd-d7845664c-rp56l in astronomer-transparent-terminator-3163 namespace
Collecting log of the container statsd in pod transparent-terminator-3163-statsd-d7845664c-rp56l in the astronomer-transparent-terminator-3163 namespace now
Starting to Collect log of the pod transparent-terminator-3163-triggerer-75995dd675-49vvq in astronomer-transparent-terminator-3163 namespace
Collecting log of the container sidecar-log-consumer in pod transparent-terminator-3163-triggerer-75995dd675-49vvq in the astronomer-transparent-terminator-3163 namespace now
Collecting log of the container triggerer in pod transparent-terminator-3163-triggerer-75995dd675-49vvq in the astronomer-transparent-terminator-3163 namespace now
Starting to Collect log of the pod transparent-terminator-3163-webserver-5cc66cb995-n8cd7 in astronomer-transparent-terminator-3163 namespace
Collecting log of the container sidecar-log-consumer in pod transparent-terminator-3163-webserver-5cc66cb995-n8cd7 in the astronomer-transparent-terminator-3163 namespace now
Collecting log of the container webserver in pod transparent-terminator-3163-webserver-5cc66cb995-n8cd7 in the astronomer-transparent-terminator-3163 namespace now
Starting to Collect log of the pod transparent-terminator-3163-worker-7557c78f59-wvkmr in astronomer-transparent-terminator-3163 namespace
Collecting log of the container sidecar-log-consumer in pod transparent-terminator-3163-worker-7557c78f59-wvkmr in the astronomer-transparent-terminator-3163 namespace now
Collecting log of the container worker in pod transparent-terminator-3163-worker-7557c78f59-wvkmr in the astronomer-transparent-terminator-3163 namespace now
Starting to Collect log of the pod cluster-autoscaler-aws-cluster-autoscaler-chart-fb79c9f7d-wfjsj in cluster-autoscaler namespace
Collecting log of the container aws-cluster-autoscaler-chart in pod cluster-autoscaler-aws-cluster-autoscaler-chart-fb79c9f7d-wfjsj in the cluster-autoscaler namespace now
No resources found in default namespace.
No resources found in kube-node-lease namespace.
No resources found in kube-public namespace.
Starting to Collect log of the pod aws-node-5tjsv in kube-system namespace
Collecting log of the container aws-node in pod aws-node-5tjsv in the kube-system namespace now
Starting to Collect log of the pod aws-node-74n4v in kube-system namespace
Collecting log of the container aws-node in pod aws-node-74n4v in the kube-system namespace now
Starting to Collect log of the pod aws-node-7wdfq in kube-system namespace
Collecting log of the container aws-node in pod aws-node-7wdfq in the kube-system namespace now
Starting to Collect log of the pod aws-node-ccw2x in kube-system namespace
Collecting log of the container aws-node in pod aws-node-ccw2x in the kube-system namespace now
Starting to Collect log of the pod aws-node-lknsp in kube-system namespace
Collecting log of the container aws-node in pod aws-node-lknsp in the kube-system namespace now
Starting to Collect log of the pod aws-node-llxhp in kube-system namespace
Collecting log of the container aws-node in pod aws-node-llxhp in the kube-system namespace now
Starting to Collect log of the pod aws-node-px8r7 in kube-system namespace
Collecting log of the container aws-node in pod aws-node-px8r7 in the kube-system namespace now
Starting to Collect log of the pod aws-node-t58tj in kube-system namespace
Collecting log of the container aws-node in pod aws-node-t58tj in the kube-system namespace now
Starting to Collect log of the pod aws-node-v6fcd in kube-system namespace
Collecting log of the container aws-node in pod aws-node-v6fcd in the kube-system namespace now
Starting to Collect log of the pod aws-node-wdlcr in kube-system namespace
Collecting log of the container aws-node in pod aws-node-wdlcr in the kube-system namespace now
Starting to Collect log of the pod coredns-699755845c-4x4h6 in kube-system namespace
Collecting log of the container coredns in pod coredns-699755845c-4x4h6 in the kube-system namespace now
Starting to Collect log of the pod coredns-699755845c-7x8pd in kube-system namespace
Collecting log of the container coredns in pod coredns-699755845c-7x8pd in the kube-system namespace now
Starting to Collect log of the pod kube-proxy-4dfkm in kube-system namespace
Collecting log of the container kube-proxy in pod kube-proxy-4dfkm in the kube-system namespace now
Starting to Collect log of the pod kube-proxy-4kszs in kube-system namespace
Collecting log of the container kube-proxy in pod kube-proxy-4kszs in the kube-system namespace now
Starting to Collect log of the pod kube-proxy-7hmhr in kube-system namespace
Collecting log of the container kube-proxy in pod kube-proxy-7hmhr in the kube-system namespace now
Starting to Collect log of the pod kube-proxy-bc9mz in kube-system namespace
Collecting log of the container kube-proxy in pod kube-proxy-bc9mz in the kube-system namespace now
Starting to Collect log of the pod kube-proxy-dg9rw in kube-system namespace
Collecting log of the container kube-proxy in pod kube-proxy-dg9rw in the kube-system namespace now
Starting to Collect log of the pod kube-proxy-gkqmm in kube-system namespace
Collecting log of the container kube-proxy in pod kube-proxy-gkqmm in the kube-system namespace now
Starting to Collect log of the pod kube-proxy-hj9kz in kube-system namespace
Collecting log of the container kube-proxy in pod kube-proxy-hj9kz in the kube-system namespace now
Starting to Collect log of the pod kube-proxy-lkllv in kube-system namespace
Collecting log of the container kube-proxy in pod kube-proxy-lkllv in the kube-system namespace now
Starting to Collect log of the pod kube-proxy-r4ldj in kube-system namespace
Collecting log of the container kube-proxy in pod kube-proxy-r4ldj in the kube-system namespace now
Starting to Collect log of the pod kube-proxy-r7nkk in kube-system namespace
Collecting log of the container kube-proxy in pod kube-proxy-r7nkk in the kube-system namespace now
======================Gathering Describe output of all the nodes======================
Collecting Describe output of Node ip-10-234-1-104.us-east-2.compute.internal
Collecting Describe output of Node ip-10-234-1-159.us-east-2.compute.internal
Collecting Describe output of Node ip-10-234-1-239.us-east-2.compute.internal
Collecting Describe output of Node ip-10-234-1-242.us-east-2.compute.internal
Collecting Describe output of Node ip-10-234-1-246.us-east-2.compute.internal
Collecting Describe output of Node ip-10-234-2-100.us-east-2.compute.internal
Collecting Describe output of Node ip-10-234-2-153.us-east-2.compute.internal
Collecting Describe output of Node ip-10-234-2-22.us-east-2.compute.internal
Collecting Describe output of Node ip-10-234-2-242.us-east-2.compute.internal
Collecting Describe output of Node ip-10-234-2-44.us-east-2.compute.internal
======================Gathering All the astronomer namespace logs======================
Gathering logs of houston in astronomer Namespace
Found 2 pods, using pod/astronomer-houston-cf67c758-4txb6
Gathering logs of houston-worker in astronomer Namespace
Found 2 pods, using pod/astronomer-houston-worker-f68cb689b-n8tqs
Gathering logs of astro-ui in astronomer Namespace
Found 2 pods, using pod/astronomer-astro-ui-5b44b44f4-vnfmc
Gathering logs of commander in astronomer Namespace
Found 2 pods, using pod/astronomer-commander-57559fc99f-vkxjb
Gathering logs of nginx in astronomer Namespace
Found 2 pods, using pod/astronomer-nginx-df4b74944-4vqfv
Gathering logs of grafana in astronomer Namespace
Gathering logs of kube-state in astronomer Namespace
Gathering logs of kibana in astronomer Namespace
Gathering logs of nginx-default-backend in astronomer Namespace
Found 2 pods, using pod/astronomer-nginx-default-backend-864d4468b8-bhl6b
Gathering logs of elasticsearch-exporterin astronomer Namespace
Gathering logs of elasticsearch-nginx in astronomer Namespace
Gathering logs of cli-install in astronomer Namespace
Gathering logs of elasticsearch-client in astronomer Namespace
Found 2 pods, using pod/astronomer-elasticsearch-client-6f8f4f5897-gzgjr
Gathering logs of elasticsearch-master in astronomer Namespace
Found 3 pods, using pod/astronomer-elasticsearch-master-0
Gathering logs of elasticsearch-data in astronomer Namespace
Found 2 pods, using pod/astronomer-elasticsearch-data-0
Gathering logs of stan in astronomer Namespace
Found 3 pods, using pod/astronomer-stan-0
Gathering logs of registry in astronomer Namespace
Gathering logs of prometheus in astronomer Namespace
Gathering logs of nats in astronomer Namespace
Found 3 pods, using pod/astronomer-nats-0
Gathering logs of alertmanager in astronomer Namespace
======================Collecting Some General enviornment Information in the astronomer======================
Gathering get all status  in astronomer Namespace
Gathering All replica status in all namespaces
Gathering Pod Running status in astronomer Namespace
Gathering events in astronomer Namespace
Gathering secrets in astronomer Namespace
Gathering Node Status
Gathering kube-system pod status
Gathering sevice Status in astronomer Namespace
Gathering persistent volume Status in astronomer Namespace
Gathering ingress Status in astronomer Namespace
Gathering cronjobs Status in astronomer Namespace
Gathering jobs Status in astronomer Namespace
Gathering Astro version status
Gathering docker version status
Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?
Gathering helm version status
Gathering helm status
Gathering helm history in astronomer Namespace
Gathering helm values from astronomer Namespace
======================Collecting Some General enviornment Information in the astronomer-extraterrestrial-meteorite-6103======================
Gathering get all status  in astronomer-extraterrestrial-meteorite-6103 Namespace
Gathering All replica status in all namespaces
Gathering Pod Running status in astronomer-extraterrestrial-meteorite-6103 Namespace
Gathering events in astronomer-extraterrestrial-meteorite-6103 Namespace
Gathering secrets in astronomer-extraterrestrial-meteorite-6103 Namespace
Gathering sevice Status in astronomer-extraterrestrial-meteorite-6103 Namespace
Gathering persistent volume Status in astronomer-extraterrestrial-meteorite-6103 Namespace
Gathering ingress Status in astronomer-extraterrestrial-meteorite-6103 Namespace
Gathering cronjobs Status in astronomer-extraterrestrial-meteorite-6103 Namespace
Gathering jobs Status in astronomer-extraterrestrial-meteorite-6103 Namespace
Exporting Release name
Your Release_Name in current namespace is extraterrestrial-meteorite-6103.
======================Gathering All the Deployment namespace logs in the astronomer-extraterrestrial-meteorite-6103======================
Gathering logs of scheduler in astronomer-extraterrestrial-meteorite-6103 Namespace
Found 2 pods, using pod/extraterrestrial-meteorite-6103-scheduler-d6f644c7d-ffrzk
Gathering logs of worker in astronomer-extraterrestrial-meteorite-6103 Namespace
Found 2 pods, using pod/extraterrestrial-meteorite-6103-worker-77fdc7d6d7-rmvtg
Gathering logs of webserverin astronomer-extraterrestrial-meteorite-6103 Namespace
Gathering logs of triggerer in astronomer-extraterrestrial-meteorite-6103 Namespace
Found 2 pods, using pod/extraterrestrial-meteorite-6103-triggerer-7fffd75596-s287g
Gathering logs of pgbouncer in astronomer-extraterrestrial-meteorite-6103 Namespace
Gathering logs of flower  in astronomer-extraterrestrial-meteorite-6103 Namespace
Gathering logs of statsd in astronomer-extraterrestrial-meteorite-6103 Namespace
Gathering logs of redis in astronomer-extraterrestrial-meteorite-6103 Namespace
Gathering helm history in astronomer-extraterrestrial-meteorite-6103 Namespace
Gathering helm values from astronomer-extraterrestrial-meteorite-6103 Namespace
======================Collecting Some General enviornment Information in the astronomer-transparent-terminator-3163======================
Gathering get all status  in astronomer-transparent-terminator-3163 Namespace
Gathering All replica status in all namespaces
Gathering Pod Running status in astronomer-transparent-terminator-3163 Namespace
Gathering events in astronomer-transparent-terminator-3163 Namespace
Gathering secrets in astronomer-transparent-terminator-3163 Namespace
Gathering sevice Status in astronomer-transparent-terminator-3163 Namespace
Gathering persistent volume Status in astronomer-transparent-terminator-3163 Namespace
Gathering ingress Status in astronomer-transparent-terminator-3163 Namespace
Gathering cronjobs Status in astronomer-transparent-terminator-3163 Namespace
Gathering jobs Status in astronomer-transparent-terminator-3163 Namespace
Exporting Release name
Your Release_Name in current namespace is transparent-terminator-3163.
======================Gathering All the Deployment namespace logs in the astronomer-transparent-terminator-3163======================
Gathering logs of scheduler in astronomer-transparent-terminator-3163 Namespace
Found 2 pods, using pod/transparent-terminator-3163-scheduler-8b6858fdf-6zbqp
Gathering logs of worker in astronomer-transparent-terminator-3163 Namespace
Gathering logs of webserverin astronomer-transparent-terminator-3163 Namespace
Gathering logs of triggerer in astronomer-transparent-terminator-3163 Namespace
Gathering logs of pgbouncer in astronomer-transparent-terminator-3163 Namespace
Gathering logs of flower  in astronomer-transparent-terminator-3163 Namespace
Gathering logs of statsd in astronomer-transparent-terminator-3163 Namespace
Gathering logs of redis in astronomer-transparent-terminator-3163 Namespace
Gathering helm history in astronomer-transparent-terminator-3163 Namespace
Gathering helm values from astronomer-transparent-terminator-3163 Namespace
Checking ENDPOINTS
======================CHECKING Houston ENDPOINT for 10.234.1.9======================
PLEASE NOTE ======== you have to run nslookup houston.nandlal51.astro-cre.com 10.234.1.9 inside any of the pods lets say inside a nginx pod to make sure endpoints are running fine
======================CHECKING Houston ENDPOINT for 10.234.2.104======================
PLEASE NOTE ======== you have to run nslookup houston.nandlal51.astro-cre.com 10.234.2.104 inside any of the pods lets say inside a nginx pod to make sure endpoints are running fine
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0   271    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0   271    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0   271    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0   271    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0   271    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0   271    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0   271    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0   271    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0   271    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0   271    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
======================creating GZ and zip files======================
tar: Removing leading `/' from member names
/tmp/astro_logs/
/tmp/astro_logs/curl_check_registry.nandlal51.astro-cre.com.log
/tmp/astro_logs/nslookup_houston_10.234.1.9.nandlal51.astro-cre.com.log
/tmp/astro_logs/curl_check_install.nandlal51.astro-cre.com.log
/tmp/astro_logs/kube-node-lease/
/tmp/astro_logs/kube-node-lease/AllPodlogs/
/tmp/astro_logs/astronomer-transparent-terminator-3163/
/tmp/astro_logs/astronomer-transparent-terminator-3163/pods_astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/webserverastronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/scheduler_astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/cronjobs_astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/rs_status_all_namespaces.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/pgbouncer _astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/secrets_astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/helm_history_transparent-terminator-3163.yaml
/tmp/astro_logs/astronomer-transparent-terminator-3163/ingress_astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/svc_astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/worker_astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/statsd_astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/getall_status_astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/helm_values_transparent-terminator-3163.yaml
/tmp/astro_logs/astronomer-transparent-terminator-3163/redis_astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/triggerer astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/flower _astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/events_astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/pvc_astronomer-transparent-terminator-3163.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-redis-0-pod_redis-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-worker-7557c78f59-wvkmr-pod_worker-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-pgbouncer-6c94bc5b99-sgkvp-pod_pgbouncer-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-webserver-5cc66cb995-n8cd7-pod_webserver-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-triggerer-75995dd675-49vvq-pod_sidecar-log-consumer-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-worker-7557c78f59-wvkmr-pod_sidecar-log-consumer-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-webserver-5cc66cb995-n8cd7-pod_sidecar-log-consumer-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-scheduler-8b6858fdf-bs6nf-pod_sidecar-log-consumer-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-scheduler-8b6858fdf-bs6nf-pod_scheduler-log-groomer-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-scheduler-8b6858fdf-bs6nf-pod_scheduler-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-scheduler-8b6858fdf-6zbqp-pod_sidecar-log-consumer-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-cleanup-27730326-msrlz-pod_airflow-cleanup-pods-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-flower-656699b5fb-2k78m-pod_flower-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-triggerer-75995dd675-49vvq-pod_triggerer-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-scheduler-8b6858fdf-6zbqp-pod_scheduler-log-groomer-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-statsd-d7845664c-rp56l-pod_statsd-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-scheduler-8b6858fdf-6zbqp-pod_scheduler-container.log
/tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-pgbouncer-6c94bc5b99-sgkvp-pod_metrics-exporter-container.log
/tmp/astro_logs/nslookup_houston_10.234.2.104.nandlal51.astro-cre.com.log
/tmp/astro_logs/astronomer/
/tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-1-246.us-east-2.compute.internal.log
/tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-2-242.us-east-2.compute.internal.log
/tmp/astro_logs/astronomer/houston-workerastronomer.log
/tmp/astro_logs/astronomer/nodes.log
/tmp/astro_logs/astronomer/nginx-default-backend_astronomer.log
/tmp/astro_logs/astronomer/alertmanager_astronomer.log
/tmp/astro_logs/astronomer/kube-state_astronomer.log
/tmp/astro_logs/astronomer/secrets_astronomer.log
/tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-2-153.us-east-2.compute.internal.log
/tmp/astro_logs/astronomer/nginx_astronomer.log
/tmp/astro_logs/astronomer/svc_astronomer.log
/tmp/astro_logs/astronomer/kibana_astronomer.log
/tmp/astro_logs/astronomer/rs_status_all_namespaces.log
/tmp/astro_logs/astronomer/ingress_astronomer.log
/tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-1-104.us-east-2.compute.internal.log
/tmp/astro_logs/astronomer/stan_contatiner_astronomer.log
/tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-1-242.us-east-2.compute.internal.log
/tmp/astro_logs/astronomer/cli-install_astronomer.log
/tmp/astro_logs/astronomer/helm_history_astronomer.log
/tmp/astro_logs/astronomer/cronjobs_astronomer.log
/tmp/astro_logs/astronomer/helm_values_astronomer.yaml
/tmp/astro_logs/astronomer/prometheus_container_astronomer.log
/tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-1-159.us-east-2.compute.internal.log
/tmp/astro_logs/astronomer/elasticsearch-master_astronomer.log
/tmp/astro_logs/astronomer/jobs_astronomer.log
/tmp/astro_logs/astronomer/helm_status.log
/tmp/astro_logs/astronomer/events_astronomer.log
/tmp/astro_logs/astronomer/kube-system.log
/tmp/astro_logs/astronomer/getall_status_astronomer.log
/tmp/astro_logs/astronomer/elasticsearch-data_astronomer.log
/tmp/astro_logs/astronomer/pvc_astronomer.log
/tmp/astro_logs/astronomer/elasticsearch-clientastronomer.log
/tmp/astro_logs/astronomer/registryastronomer.log
/tmp/astro_logs/astronomer/commanderastronomer.log
/tmp/astro_logs/astronomer/nats_astronomer.log
/tmp/astro_logs/astronomer/houstonastronomer.log
/tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-1-239.us-east-2.compute.internal.log
/tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-2-22.us-east-2.compute.internal.log
/tmp/astro_logs/astronomer/elasticsearch-nginx_astronomer.log
/tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-2-44.us-east-2.compute.internal.log
/tmp/astro_logs/astronomer/astro-uiastronomer.log
/tmp/astro_logs/astronomer/pods_astronomer.log
/tmp/astro_logs/astronomer/Enviornment_Info.log
/tmp/astro_logs/astronomer/grafana_astronomer.log
/tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-2-100.us-east-2.compute.internal.log
/tmp/astro_logs/astronomer/AllPodlogs/
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-commander-57559fc99f-vkxjb-pod_commander-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-grafana-957c66f47-bvwjz-pod_grafana-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-nginx-default-backend-864d4468b8-2tggh-pod_default-backend-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-runtime-check-27727243-lkpkc-pod_update-check-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-nats-0-pod_nats-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-nats-2-pod_metrics-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-runtime-check-27730123-55w6l-pod_update-check-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-airflow-check-27730317-dv47f-pod_update-check-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-0-pod_configmap-reloader-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-cleanup-deployments-27728640-2q6wl-pod_cleanup-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-check-27727200-vpwn6-pod_update-check-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-0-pod_prometheus-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-worker-f68cb689b-n8tqs-pod_houston-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-check-27728640-mnrmq-pod_update-check-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-worker-f68cb689b-w74lb-pod_houston-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-stan-0-pod_stan-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-dxr97-pod_node-exporter-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-kibana-5c49d7fd5f-rwsbp-pod_kibana-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-x8b2g-pod_node-exporter-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-cleanup-deployments-27730080-72sxq-pod_cleanup-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-nginx-default-backend-864d4468b8-bhl6b-pod_default-backend-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-config-syncer-27729138-sppns-pod_config-syncer-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-curator-27730140-q4nfm-pod_curator-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-data-0-pod_es-data-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-client-6f8f4f5897-2x85r-pod_es-client-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-nats-0-pod_metrics-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-nginx-859958bd58-vb7g7-pod_nginx-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-cleanup-deployments-27727200-v49t2-pod_cleanup-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-curator-27728700-t69hz-pod_curator-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-nginx-df4b74944-4ktlc-pod_nginx-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-stan-2-pod_stan-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-exporter-8647676d-7dpqp-pod_metrics-exporter-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-nginx-df4b74944-4vqfv-pod_nginx-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-commander-57559fc99f-dfc5b-pod_commander-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-cf67c758-4txb6-pod_houston-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-7crxk-pod_node-exporter-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-alertmanager-0-pod_alertmanager-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-astro-ui-5b44b44f4-rnq84-pod_astro-ui-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-check-27730080-hnb5c-pod_update-check-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-client-6f8f4f5897-gzgjr-pod_es-client-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-lnfhm-pod_node-exporter-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-nats-2-pod_nats-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-2g5mz-pod_node-exporter-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-cli-install-9c6dc84f7-sf8vp-pod_cli-install-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-data-1-pod_es-data-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-stan-1-pod_metrics-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-registry-0-pod_registry-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-runtime-check-27728683-dsppq-pod_update-check-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-nats-1-pod_nats-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-nats-1-pod_metrics-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-airflow-check-27730257-wwb4f-pod_update-check-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-stan-0-pod_metrics-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-config-syncer-27727698-r4w4k-pod_config-syncer-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-5ck9d-pod_node-exporter-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-master-1-pod_es-master-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-g22qd-pod_node-exporter-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-curator-27727260-nffh7-pod_curator-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-kube-state-7fcbd4fb88-cjxf8-pod_kube-state-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-stan-2-pod_metrics-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-astro-ui-5b44b44f4-vnfmc-pod_astro-ui-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-stan-1-pod_stan-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-airflow-check-27730197-j28qp-pod_update-check-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-49bgn-pod_node-exporter-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-ldj66-pod_node-exporter-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-cf67c758-nkxsg-pod_houston-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-hw4tv-pod_node-exporter-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-master-2-pod_es-master-container.log
/tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-master-0-pod_es-master-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/webserverastronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/triggerer astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/pods_astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/rs_status_all_namespaces.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/pvc_astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/events_astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/getall_status_astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/statsd_astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/secrets_astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/helm_values_extraterrestrial-meteorite-6103.yaml
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/pgbouncer _astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/svc_astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/helm_history_extraterrestrial-meteorite-6103.yaml
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/ingress_astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b-BAD_astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/cronjobs_astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/worker_astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/extraterrestrial-meteorite-6103-triggerer-5f8fd74c55-cj67f-BAD_astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/scheduler_astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/flower _astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/redis_astronomer-extraterrestrial-meteorite-6103.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-statsd-78bfc6db4f-kqbfw-pod_statsd-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-redis-0-pod_redis-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-flower-b58f9cc5d-mp86c-pod_flower-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b-pod_sidecar-log-consumer-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-scheduler-d6f644c7d-tvs6n-pod_scheduler-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-pgbouncer-778666fbf4-5f4ls-pod_pgbouncer-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-scheduler-d6f644c7d-ffrzk-pod_scheduler-log-groomer-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-webserver-7869b4d57f-kpftf-pod_webserver-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-triggerer-7fffd75596-s287g-pod_sidecar-log-consumer-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-scheduler-d6f644c7d-ffrzk-pod_scheduler-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-triggerer-5f8fd74c55-cj67f-pod_triggerer-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-scheduler-d6f644c7d-tvs6n-pod_scheduler-log-groomer-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-worker-77fdc7d6d7-rmvtg-pod_worker-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-pgbouncer-778666fbf4-5f4ls-pod_metrics-exporter-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-triggerer-5f8fd74c55-cj67f-pod_sidecar-log-consumer-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-cleanup-27730326-xzq87-pod_airflow-cleanup-pods-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-scheduler-d6f644c7d-ffrzk-pod_sidecar-log-consumer-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b-pod_worker-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-webserver-7869b4d57f-kpftf-pod_sidecar-log-consumer-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-worker-77fdc7d6d7-rmvtg-pod_sidecar-log-consumer-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-triggerer-7fffd75596-s287g-pod_triggerer-container.log
/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-scheduler-d6f644c7d-tvs6n-pod_sidecar-log-consumer-container.log
/tmp/astro_logs/kube-system/
/tmp/astro_logs/kube-system/AllPodlogs/
/tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-dg9rw-pod_kube-proxy-container.log
/tmp/astro_logs/kube-system/AllPodlogs/coredns-699755845c-7x8pd-pod_coredns-container.log
/tmp/astro_logs/kube-system/AllPodlogs/aws-node-ccw2x-pod_aws-node-container.log
/tmp/astro_logs/kube-system/AllPodlogs/coredns-699755845c-4x4h6-pod_coredns-container.log
/tmp/astro_logs/kube-system/AllPodlogs/aws-node-lknsp-pod_aws-node-container.log
/tmp/astro_logs/kube-system/AllPodlogs/aws-node-px8r7-pod_aws-node-container.log
/tmp/astro_logs/kube-system/AllPodlogs/aws-node-5tjsv-pod_aws-node-container.log
/tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-4dfkm-pod_kube-proxy-container.log
/tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-7hmhr-pod_kube-proxy-container.log
/tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-4kszs-pod_kube-proxy-container.log
/tmp/astro_logs/kube-system/AllPodlogs/aws-node-llxhp-pod_aws-node-container.log
/tmp/astro_logs/kube-system/AllPodlogs/aws-node-wdlcr-pod_aws-node-container.log
/tmp/astro_logs/kube-system/AllPodlogs/aws-node-v6fcd-pod_aws-node-container.log
/tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-bc9mz-pod_kube-proxy-container.log
/tmp/astro_logs/kube-system/AllPodlogs/aws-node-7wdfq-pod_aws-node-container.log
/tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-gkqmm-pod_kube-proxy-container.log
/tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-hj9kz-pod_kube-proxy-container.log
/tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-r4ldj-pod_kube-proxy-container.log
/tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-lkllv-pod_kube-proxy-container.log
/tmp/astro_logs/kube-system/AllPodlogs/aws-node-t58tj-pod_aws-node-container.log
/tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-r7nkk-pod_kube-proxy-container.log
/tmp/astro_logs/kube-system/AllPodlogs/aws-node-74n4v-pod_aws-node-container.log
/tmp/astro_logs/default/
/tmp/astro_logs/default/AllPodlogs/
/tmp/astro_logs/cluster-autoscaler/
/tmp/astro_logs/cluster-autoscaler/AllPodlogs/
/tmp/astro_logs/cluster-autoscaler/AllPodlogs/cluster-autoscaler-aws-cluster-autoscaler-chart-fb79c9f7d-wfjsj-pod_aws-cluster-autoscaler-chart-container.log
/tmp/astro_logs/kube-public/
/tmp/astro_logs/kube-public/AllPodlogs/
/tmp/astro_logs/curl_check_app.nandlal51.astro-cre.com.log
/tmp/astro_logs/astro_logs_2022-09-22.tar.gz
tar: /tmp/astro_logs/astro_logs_2022-09-22.tar.gz: file changed as we read it
  adding: tmp/astro_logs/ (stored 0%)
  adding: tmp/astro_logs/curl_check_registry.nandlal51.astro-cre.com.log (deflated 94%)
  adding: tmp/astro_logs/nslookup_houston_10.234.1.9.nandlal51.astro-cre.com.log (deflated 62%)
  adding: tmp/astro_logs/curl_check_install.nandlal51.astro-cre.com.log (deflated 94%)
  adding: tmp/astro_logs/kube-node-lease/ (stored 0%)
  adding: tmp/astro_logs/kube-node-lease/AllPodlogs/ (stored 0%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/ (stored 0%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/pods_astronomer-transparent-terminator-3163.log (deflated 77%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/webserverastronomer-transparent-terminator-3163.log (deflated 97%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/scheduler_astronomer-transparent-terminator-3163.log (deflated 89%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/cronjobs_astronomer-transparent-terminator-3163.log (deflated 62%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/rs_status_all_namespaces.log (deflated 70%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/pgbouncer _astronomer-transparent-terminator-3163.log (deflated 84%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/secrets_astronomer-transparent-terminator-3163.log (deflated 84%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/helm_history_transparent-terminator-3163.yaml (deflated 23%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/ingress_astronomer-transparent-terminator-3163.log (deflated 69%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/svc_astronomer-transparent-terminator-3163.log (deflated 67%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/worker_astronomer-transparent-terminator-3163.log (deflated 96%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/statsd_astronomer-transparent-terminator-3163.log (deflated 48%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/getall_status_astronomer-transparent-terminator-3163.log (deflated 80%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/helm_values_transparent-terminator-3163.yaml (deflated 79%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/redis_astronomer-transparent-terminator-3163.log (deflated 68%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/triggerer astronomer-transparent-terminator-3163.log (deflated 69%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/flower _astronomer-transparent-terminator-3163.log (deflated 72%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/events_astronomer-transparent-terminator-3163.log (deflated 86%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/pvc_astronomer-transparent-terminator-3163.log (deflated 43%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/ (stored 0%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-redis-0-pod_redis-container.log (deflated 68%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-worker-7557c78f59-wvkmr-pod_worker-container.log (deflated 96%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-pgbouncer-6c94bc5b99-sgkvp-pod_pgbouncer-container.log (deflated 84%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-webserver-5cc66cb995-n8cd7-pod_webserver-container.log (deflated 96%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-triggerer-75995dd675-49vvq-pod_sidecar-log-consumer-container.log (deflated 68%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-worker-7557c78f59-wvkmr-pod_sidecar-log-consumer-container.log (deflated 93%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-webserver-5cc66cb995-n8cd7-pod_sidecar-log-consumer-container.log (deflated 68%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-scheduler-8b6858fdf-bs6nf-pod_sidecar-log-consumer-container.log (deflated 94%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-scheduler-8b6858fdf-bs6nf-pod_scheduler-log-groomer-container.log (deflated 99%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-scheduler-8b6858fdf-bs6nf-pod_scheduler-container.log (deflated 89%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-scheduler-8b6858fdf-6zbqp-pod_sidecar-log-consumer-container.log (deflated 94%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-cleanup-27730326-msrlz-pod_airflow-cleanup-pods-container.log (deflated 90%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-flower-656699b5fb-2k78m-pod_flower-container.log (deflated 72%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-triggerer-75995dd675-49vvq-pod_triggerer-container.log (deflated 69%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-scheduler-8b6858fdf-6zbqp-pod_scheduler-log-groomer-container.log (deflated 99%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-statsd-d7845664c-rp56l-pod_statsd-container.log (deflated 48%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-scheduler-8b6858fdf-6zbqp-pod_scheduler-container.log (deflated 89%)
  adding: tmp/astro_logs/astronomer-transparent-terminator-3163/AllPodlogs/transparent-terminator-3163-pgbouncer-6c94bc5b99-sgkvp-pod_metrics-exporter-container.log (deflated 33%)
  adding: tmp/astro_logs/nslookup_houston_10.234.2.104.nandlal51.astro-cre.com.log (deflated 63%)
  adding: tmp/astro_logs/astronomer/ (stored 0%)
  adding: tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-1-246.us-east-2.compute.internal.log (deflated 72%)
  adding: tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-2-242.us-east-2.compute.internal.log (deflated 72%)
  adding: tmp/astro_logs/astronomer/houston-workerastronomer.log (deflated 88%)
  adding: tmp/astro_logs/astronomer/nodes.log (deflated 85%)
  adding: tmp/astro_logs/astronomer/nginx-default-backend_astronomer.log (deflated 97%)
  adding: tmp/astro_logs/astronomer/alertmanager_astronomer.log (deflated 61%)
  adding: tmp/astro_logs/astronomer/kube-state_astronomer.log (deflated 55%)
  adding: tmp/astro_logs/astronomer/secrets_astronomer.log (deflated 85%)
  adding: tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-2-153.us-east-2.compute.internal.log (deflated 72%)
  adding: tmp/astro_logs/astronomer/nginx_astronomer.log (deflated 94%)
  adding: tmp/astro_logs/astronomer/svc_astronomer.log (deflated 85%)
  adding: tmp/astro_logs/astronomer/kibana_astronomer.log (deflated 98%)
  adding: tmp/astro_logs/astronomer/rs_status_all_namespaces.log (deflated 84%)
  adding: tmp/astro_logs/astronomer/ingress_astronomer.log (deflated 83%)
  adding: tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-1-104.us-east-2.compute.internal.log (deflated 72%)
  adding: tmp/astro_logs/astronomer/stan_contatiner_astronomer.log (deflated 88%)
  adding: tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-1-242.us-east-2.compute.internal.log (deflated 71%)
  adding: tmp/astro_logs/astronomer/cli-install_astronomer.log (deflated 97%)
  adding: tmp/astro_logs/astronomer/helm_history_astronomer.log (deflated 74%)
  adding: tmp/astro_logs/astronomer/cronjobs_astronomer.log (deflated 67%)
  adding: tmp/astro_logs/astronomer/helm_values_astronomer.yaml (deflated 44%)
  adding: tmp/astro_logs/astronomer/prometheus_container_astronomer.log (deflated 86%)
  adding: tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-1-159.us-east-2.compute.internal.log (deflated 70%)
  adding: tmp/astro_logs/astronomer/elasticsearch-master_astronomer.log (deflated 88%)
  adding: tmp/astro_logs/astronomer/jobs_astronomer.log (deflated 79%)
  adding: tmp/astro_logs/astronomer/helm_status.log (deflated 64%)
  adding: tmp/astro_logs/astronomer/events_astronomer.log (deflated 76%)
  adding: tmp/astro_logs/astronomer/kube-system.log (deflated 86%)
  adding: tmp/astro_logs/astronomer/getall_status_astronomer.log (deflated 91%)
  adding: tmp/astro_logs/astronomer/elasticsearch-data_astronomer.log (deflated 87%)
  adding: tmp/astro_logs/astronomer/pvc_astronomer.log (deflated 70%)
  adding: tmp/astro_logs/astronomer/elasticsearch-clientastronomer.log (deflated 90%)
  adding: tmp/astro_logs/astronomer/registryastronomer.log (deflated 98%)
  adding: tmp/astro_logs/astronomer/commanderastronomer.log (deflated 91%)
  adding: tmp/astro_logs/astronomer/nats_astronomer.log (deflated 74%)
  adding: tmp/astro_logs/astronomer/houstonastronomer.log (deflated 93%)
  adding: tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-1-239.us-east-2.compute.internal.log (deflated 71%)
  adding: tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-2-22.us-east-2.compute.internal.log (deflated 73%)
  adding: tmp/astro_logs/astronomer/elasticsearch-nginx_astronomer.log (deflated 98%)
  adding: tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-2-44.us-east-2.compute.internal.log (deflated 71%)
  adding: tmp/astro_logs/astronomer/astro-uiastronomer.log (deflated 98%)
  adding: tmp/astro_logs/astronomer/pods_astronomer.log (deflated 88%)
  adding: tmp/astro_logs/astronomer/Enviornment_Info.log (deflated 59%)
  adding: tmp/astro_logs/astronomer/grafana_astronomer.log (deflated 93%)
  adding: tmp/astro_logs/astronomer/DESCRIBE_ip-10-234-2-100.us-east-2.compute.internal.log (deflated 72%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/ (stored 0%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-commander-57559fc99f-vkxjb-pod_commander-container.log (deflated 91%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-grafana-957c66f47-bvwjz-pod_grafana-container.log (deflated 75%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-nginx-default-backend-864d4468b8-2tggh-pod_default-backend-container.log (deflated 97%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-runtime-check-27727243-lkpkc-pod_update-check-container.log (deflated 91%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-nats-0-pod_nats-container.log (deflated 74%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-nats-2-pod_metrics-container.log (deflated 7%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-runtime-check-27730123-55w6l-pod_update-check-container.log (deflated 91%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-airflow-check-27730317-dv47f-pod_update-check-container.log (deflated 95%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-0-pod_configmap-reloader-container.log (deflated 39%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-cleanup-deployments-27728640-2q6wl-pod_cleanup-container.log (deflated 58%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-check-27727200-vpwn6-pod_update-check-container.log (deflated 74%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-0-pod_prometheus-container.log (deflated 86%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-worker-f68cb689b-n8tqs-pod_houston-container.log (deflated 88%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-check-27728640-mnrmq-pod_update-check-container.log (deflated 74%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-worker-f68cb689b-w74lb-pod_houston-container.log (deflated 90%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-stan-0-pod_stan-container.log (deflated 88%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-dxr97-pod_node-exporter-container.log (deflated 83%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-kibana-5c49d7fd5f-rwsbp-pod_kibana-container.log (deflated 98%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-x8b2g-pod_node-exporter-container.log (deflated 83%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-cleanup-deployments-27730080-72sxq-pod_cleanup-container.log (deflated 57%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-nginx-default-backend-864d4468b8-bhl6b-pod_default-backend-container.log (deflated 97%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-config-syncer-27729138-sppns-pod_config-syncer-container.log (deflated 60%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-curator-27730140-q4nfm-pod_curator-container.log (deflated 61%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-data-0-pod_es-data-container.log (deflated 87%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-client-6f8f4f5897-2x85r-pod_es-client-container.log (deflated 91%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-nats-0-pod_metrics-container.log (deflated 7%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-nginx-859958bd58-vb7g7-pod_nginx-container.log (deflated 98%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-cleanup-deployments-27727200-v49t2-pod_cleanup-container.log (deflated 57%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-curator-27728700-t69hz-pod_curator-container.log (deflated 61%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-nginx-df4b74944-4ktlc-pod_nginx-container.log (deflated 94%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-stan-2-pod_stan-container.log (deflated 88%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-exporter-8647676d-7dpqp-pod_metrics-exporter-container.log (deflated 93%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-nginx-df4b74944-4vqfv-pod_nginx-container.log (deflated 94%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-commander-57559fc99f-dfc5b-pod_commander-container.log (deflated 92%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-cf67c758-4txb6-pod_houston-container.log (deflated 93%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-7crxk-pod_node-exporter-container.log (deflated 83%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-alertmanager-0-pod_alertmanager-container.log (deflated 61%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-astro-ui-5b44b44f4-rnq84-pod_astro-ui-container.log (deflated 98%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-check-27730080-hnb5c-pod_update-check-container.log (deflated 74%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-client-6f8f4f5897-gzgjr-pod_es-client-container.log (deflated 90%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-lnfhm-pod_node-exporter-container.log (deflated 83%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-nats-2-pod_nats-container.log (deflated 71%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-2g5mz-pod_node-exporter-container.log (deflated 83%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-cli-install-9c6dc84f7-sf8vp-pod_cli-install-container.log (deflated 97%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-data-1-pod_es-data-container.log (deflated 86%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-stan-1-pod_metrics-container.log (deflated 5%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-registry-0-pod_registry-container.log (deflated 98%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-runtime-check-27728683-dsppq-pod_update-check-container.log (deflated 91%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-nats-1-pod_nats-container.log (deflated 74%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-nats-1-pod_metrics-container.log (deflated 6%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-airflow-check-27730257-wwb4f-pod_update-check-container.log (deflated 95%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-stan-0-pod_metrics-container.log (deflated 5%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-config-syncer-27727698-r4w4k-pod_config-syncer-container.log (deflated 60%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-5ck9d-pod_node-exporter-container.log (deflated 83%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-master-1-pod_es-master-container.log (deflated 88%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-g22qd-pod_node-exporter-container.log (deflated 83%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-curator-27727260-nffh7-pod_curator-container.log (deflated 61%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-kube-state-7fcbd4fb88-cjxf8-pod_kube-state-container.log (deflated 55%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-stan-2-pod_metrics-container.log (deflated 5%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-astro-ui-5b44b44f4-vnfmc-pod_astro-ui-container.log (deflated 98%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-stan-1-pod_stan-container.log (deflated 88%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-update-airflow-check-27730197-j28qp-pod_update-check-container.log (deflated 95%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-49bgn-pod_node-exporter-container.log (deflated 83%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-ldj66-pod_node-exporter-container.log (deflated 83%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-houston-cf67c758-nkxsg-pod_houston-container.log (deflated 93%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-prometheus-node-exporter-hw4tv-pod_node-exporter-container.log (deflated 83%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-master-2-pod_es-master-container.log (deflated 85%)
  adding: tmp/astro_logs/astronomer/AllPodlogs/astronomer-elasticsearch-master-0-pod_es-master-container.log (deflated 88%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/ (stored 0%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/webserverastronomer-extraterrestrial-meteorite-6103.log (deflated 97%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/triggerer astronomer-extraterrestrial-meteorite-6103.log (deflated 74%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/pods_astronomer-extraterrestrial-meteorite-6103.log (deflated 78%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/rs_status_all_namespaces.log (deflated 73%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/pvc_astronomer-extraterrestrial-meteorite-6103.log (deflated 43%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/events_astronomer-extraterrestrial-meteorite-6103.log (deflated 86%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/getall_status_astronomer-extraterrestrial-meteorite-6103.log (deflated 81%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/statsd_astronomer-extraterrestrial-meteorite-6103.log (deflated 48%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/secrets_astronomer-extraterrestrial-meteorite-6103.log (deflated 84%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/helm_values_extraterrestrial-meteorite-6103.yaml (deflated 79%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/pgbouncer _astronomer-extraterrestrial-meteorite-6103.log (deflated 87%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/svc_astronomer-extraterrestrial-meteorite-6103.log (deflated 67%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/helm_history_extraterrestrial-meteorite-6103.yaml (deflated 24%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/ingress_astronomer-extraterrestrial-meteorite-6103.log (deflated 70%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b-BAD_astronomer-extraterrestrial-meteorite-6103.log (deflated 74%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/cronjobs_astronomer-extraterrestrial-meteorite-6103.log (deflated 62%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/worker_astronomer-extraterrestrial-meteorite-6103.log (deflated 96%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/extraterrestrial-meteorite-6103-triggerer-5f8fd74c55-cj67f-BAD_astronomer-extraterrestrial-meteorite-6103.log (deflated 73%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/scheduler_astronomer-extraterrestrial-meteorite-6103.log (deflated 92%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/flower _astronomer-extraterrestrial-meteorite-6103.log (deflated 72%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/redis_astronomer-extraterrestrial-meteorite-6103.log (deflated 89%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/ (stored 0%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-statsd-78bfc6db4f-kqbfw-pod_statsd-container.log (deflated 48%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-redis-0-pod_redis-container.log (deflated 89%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-flower-b58f9cc5d-mp86c-pod_flower-container.log (deflated 72%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b-pod_sidecar-log-consumer-container.log (stored 0%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-scheduler-d6f644c7d-tvs6n-pod_scheduler-container.log (deflated 93%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-pgbouncer-778666fbf4-5f4ls-pod_pgbouncer-container.log (deflated 87%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-scheduler-d6f644c7d-ffrzk-pod_scheduler-log-groomer-container.log (deflated 100%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-webserver-7869b4d57f-kpftf-pod_webserver-container.log (deflated 97%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-triggerer-7fffd75596-s287g-pod_sidecar-log-consumer-container.log (deflated 68%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-scheduler-d6f644c7d-ffrzk-pod_scheduler-container.log (deflated 92%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-triggerer-5f8fd74c55-cj67f-pod_triggerer-container.log (stored 0%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-scheduler-d6f644c7d-tvs6n-pod_scheduler-log-groomer-container.log (deflated 100%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-worker-77fdc7d6d7-rmvtg-pod_worker-container.log (deflated 96%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-pgbouncer-778666fbf4-5f4ls-pod_metrics-exporter-container.log (deflated 33%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-triggerer-5f8fd74c55-cj67f-pod_sidecar-log-consumer-container.log (deflated 55%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-cleanup-27730326-xzq87-pod_airflow-cleanup-pods-container.log (deflated 90%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-scheduler-d6f644c7d-ffrzk-pod_sidecar-log-consumer-container.log (deflated 97%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b-pod_worker-container.log (stored 0%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-webserver-7869b4d57f-kpftf-pod_sidecar-log-consumer-container.log (deflated 68%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-worker-77fdc7d6d7-rmvtg-pod_sidecar-log-consumer-container.log (deflated 97%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-triggerer-7fffd75596-s287g-pod_triggerer-container.log (deflated 74%)
  adding: tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103/AllPodlogs/extraterrestrial-meteorite-6103-scheduler-d6f644c7d-tvs6n-pod_sidecar-log-consumer-container.log (deflated 97%)
  adding: tmp/astro_logs/kube-system/ (stored 0%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/ (stored 0%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-dg9rw-pod_kube-proxy-container.log (deflated 87%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/coredns-699755845c-7x8pd-pod_coredns-container.log (deflated 5%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/aws-node-ccw2x-pod_aws-node-container.log (deflated 70%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/coredns-699755845c-4x4h6-pod_coredns-container.log (deflated 5%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/aws-node-lknsp-pod_aws-node-container.log (deflated 69%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/aws-node-px8r7-pod_aws-node-container.log (deflated 70%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/aws-node-5tjsv-pod_aws-node-container.log (deflated 70%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-4dfkm-pod_kube-proxy-container.log (deflated 87%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-7hmhr-pod_kube-proxy-container.log (deflated 87%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-4kszs-pod_kube-proxy-container.log (deflated 87%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/aws-node-llxhp-pod_aws-node-container.log (deflated 69%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/aws-node-wdlcr-pod_aws-node-container.log (deflated 69%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/aws-node-v6fcd-pod_aws-node-container.log (deflated 70%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-bc9mz-pod_kube-proxy-container.log (deflated 87%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/aws-node-7wdfq-pod_aws-node-container.log (deflated 69%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-gkqmm-pod_kube-proxy-container.log (deflated 87%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-hj9kz-pod_kube-proxy-container.log (deflated 87%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-r4ldj-pod_kube-proxy-container.log (deflated 87%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-lkllv-pod_kube-proxy-container.log (deflated 87%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/aws-node-t58tj-pod_aws-node-container.log (deflated 72%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/kube-proxy-r7nkk-pod_kube-proxy-container.log (deflated 87%)
  adding: tmp/astro_logs/kube-system/AllPodlogs/aws-node-74n4v-pod_aws-node-container.log (deflated 69%)
  adding: tmp/astro_logs/default/ (stored 0%)
  adding: tmp/astro_logs/default/AllPodlogs/ (stored 0%)
  adding: tmp/astro_logs/cluster-autoscaler/ (stored 0%)
  adding: tmp/astro_logs/cluster-autoscaler/AllPodlogs/ (stored 0%)
  adding: tmp/astro_logs/cluster-autoscaler/AllPodlogs/cluster-autoscaler-aws-cluster-autoscaler-chart-fb79c9f7d-wfjsj-pod_aws-cluster-autoscaler-chart-container.log (deflated 94%)
  adding: tmp/astro_logs/kube-public/ (stored 0%)
  adding: tmp/astro_logs/kube-public/AllPodlogs/ (stored 0%)
  adding: tmp/astro_logs/curl_check_app.nandlal51.astro-cre.com.log (deflated 94%)
  adding: tmp/astro_logs/astro_logs_2022-09-22.tar.gz (deflated 11%)
Here is the list of files created:
-rw-r--r-- 1 root root  721 Sep 22 09:58 /tmp/astro_logs/nslookup_houston_10.234.1.9.nandlal51.astro-cre.com.log
-rw-r--r-- 1 root root  723 Sep 22 09:58 /tmp/astro_logs/nslookup_houston_10.234.2.104.nandlal51.astro-cre.com.log
-rw-r--r-- 1 root root  12K Sep 22 09:58 /tmp/astro_logs/curl_check_registry.nandlal51.astro-cre.com.log
-rw-r--r-- 1 root root  13K Sep 22 09:58 /tmp/astro_logs/curl_check_app.nandlal51.astro-cre.com.log
-rw-r--r-- 1 root root  13K Sep 22 09:59 /tmp/astro_logs/curl_check_install.nandlal51.astro-cre.com.log
-rw-r--r-- 1 root root 8.9M Sep 22 09:59 /tmp/astro_logs/astro_logs_2022-09-22.tar.gz
-rw-r--r-- 1 root root  13M Sep 22 09:59 /tmp/astro_logs/astro_logs_2022-09-22.zip

/tmp/astro_logs/kube-system:
total 4.0K
drwxr-xr-x 2 root root 4.0K Sep 22 09:53 AllPodlogs

/tmp/astro_logs/kube-public:
total 4.0K
drwxr-xr-x 2 root root 4.0K Sep 22 09:43 AllPodlogs

/tmp/astro_logs/kube-node-lease:
total 4.0K
drwxr-xr-x 2 root root 4.0K Sep 22 09:43 AllPodlogs

/tmp/astro_logs/default:
total 4.0K
drwxr-xr-x 2 root root 4.0K Sep 22 09:43 AllPodlogs

/tmp/astro_logs/cluster-autoscaler:
total 4.0K
drwxr-xr-x 2 root root 4.0K Sep 22 09:51 AllPodlogs

/tmp/astro_logs/astronomer:
total 30M
drwxr-xr-x 2 root root  12K Sep 22 09:49 AllPodlogs
-rw-r--r-- 1 root root 5.8K Sep 22 09:53 DESCRIBE_ip-10-234-1-104.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 5.1K Sep 22 09:53 DESCRIBE_ip-10-234-1-159.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 5.8K Sep 22 09:53 DESCRIBE_ip-10-234-1-239.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 5.3K Sep 22 09:53 DESCRIBE_ip-10-234-1-242.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 5.8K Sep 22 09:53 DESCRIBE_ip-10-234-1-246.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 5.9K Sep 22 09:53 DESCRIBE_ip-10-234-2-100.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 5.6K Sep 22 09:53 DESCRIBE_ip-10-234-2-153.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 6.6K Sep 22 09:54 DESCRIBE_ip-10-234-2-22.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 6.2K Sep 22 09:54 DESCRIBE_ip-10-234-2-242.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 5.2K Sep 22 09:54 DESCRIBE_ip-10-234-2-44.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 3.7M Sep 22 09:54 houstonastronomer.log
-rw-r--r-- 1 root root  20K Sep 22 09:54 houston-workerastronomer.log
-rw-r--r-- 1 root root 3.4M Sep 22 09:54 astro-uiastronomer.log
-rw-r--r-- 1 root root 3.1M Sep 22 09:54 commanderastronomer.log
-rw-r--r-- 1 root root 1.9M Sep 22 09:54 nginx_astronomer.log
-rw-r--r-- 1 root root 1.7K Sep 22 09:54 kube-state_astronomer.log
-rw-r--r-- 1 root root 3.7M Sep 22 09:54 kibana_astronomer.log
-rw-r--r-- 1 root root 1.8M Sep 22 09:54 nginx-default-backend_astronomer.log
-rw-r--r-- 1 root root  79K Sep 22 09:54 grafana_astronomer.log
-rw-r--r-- 1 root root 6.2M Sep 22 09:54 elasticsearch-nginx_astronomer.log
-rw-r--r-- 1 root root 1.7M Sep 22 09:54 cli-install_astronomer.log
-rw-r--r-- 1 root root  63K Sep 22 09:55 elasticsearch-clientastronomer.log
-rw-r--r-- 1 root root  36K Sep 22 09:55 elasticsearch-master_astronomer.log
-rw-r--r-- 1 root root  35K Sep 22 09:55 elasticsearch-data_astronomer.log
-rw-r--r-- 1 root root 175K Sep 22 09:55 stan_contatiner_astronomer.log
-rw-r--r-- 1 root root 3.2M Sep 22 09:55 registryastronomer.log
-rw-r--r-- 1 root root  38K Sep 22 09:55 prometheus_container_astronomer.log
-rw-r--r-- 1 root root 3.2K Sep 22 09:55 nats_astronomer.log
-rw-r--r-- 1 root root 1.4K Sep 22 09:55 alertmanager_astronomer.log
-rw-r--r-- 1 root root  51K Sep 22 09:55 getall_status_astronomer.log
-rw-r--r-- 1 root root 4.3K Sep 22 09:55 rs_status_all_namespaces.log
-rw-r--r-- 1 root root  12K Sep 22 09:55 pods_astronomer.log
-rw-r--r-- 1 root root 1.6K Sep 22 09:55 events_astronomer.log
-rw-r--r-- 1 root root 2.9K Sep 22 09:55 secrets_astronomer.log
-rw-r--r-- 1 root root 2.1K Sep 22 09:56 nodes.log
-rw-r--r-- 1 root root 3.3K Sep 22 09:56 kube-system.log
-rw-r--r-- 1 root root 4.4K Sep 22 09:56 svc_astronomer.log
-rw-r--r-- 1 root root 1.7K Sep 22 09:56 pvc_astronomer.log
-rw-r--r-- 1 root root 1.6K Sep 22 09:56 ingress_astronomer.log
-rw-r--r-- 1 root root  658 Sep 22 09:56 cronjobs_astronomer.log
-rw-r--r-- 1 root root 1.7K Sep 22 09:56 jobs_astronomer.log
-rw-r--r-- 1 root root  873 Sep 22 09:56 Enviornment_Info.log
-rw-r--r-- 1 root root  880 Sep 22 09:56 helm_status.log
-rw-r--r-- 1 root root 1012 Sep 22 09:56 helm_history_astronomer.log
-rw-r--r-- 1 root root  579 Sep 22 09:56 helm_values_astronomer.yaml

/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103:
total 11M
-rw-r--r-- 1 root root 9.8K Sep 22 09:43  extraterrestrial-meteorite-6103-triggerer-5f8fd74c55-cj67f-BAD_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root 9.6K Sep 22 09:43  extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b-BAD_astronomer-extraterrestrial-meteorite-6103.log
drwxr-xr-x 2 root root 4.0K Sep 22 09:50  AllPodlogs
-rw-r--r-- 1 root root 4.9K Sep 22 09:56  getall_status_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root  879 Sep 22 09:56  rs_status_all_namespaces.log
-rw-r--r-- 1 root root 2.6K Sep 22 09:56  pods_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root 7.0K Sep 22 09:56  events_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root 2.8K Sep 22 09:56  secrets_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root  783 Sep 22 09:56  svc_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root  297 Sep 22 09:56  pvc_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root  746 Sep 22 09:56  ingress_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root  322 Sep 22 09:56  cronjobs_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root 1.1M Sep 22 09:56  scheduler_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root 4.9M Sep 22 09:57  worker_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root 4.3M Sep 22 09:57  webserverastronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root 3.1K Sep 22 09:57 'triggerer astronomer-extraterrestrial-meteorite-6103.log'
-rw-r--r-- 1 root root 396K Sep 22 09:57 'pgbouncer _astronomer-extraterrestrial-meteorite-6103.log'
-rw-r--r-- 1 root root 3.1K Sep 22 09:57 'flower _astronomer-extraterrestrial-meteorite-6103.log'
-rw-r--r-- 1 root root  568 Sep 22 09:57  statsd_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root  26K Sep 22 09:57  redis_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root  172 Sep 22 09:57  helm_history_extraterrestrial-meteorite-6103.yaml
-rw-r--r-- 1 root root  19K Sep 22 09:57  helm_values_extraterrestrial-meteorite-6103.yaml

/tmp/astro_logs/astronomer-transparent-terminator-3163:
total 1.4M
drwxr-xr-x 2 root root 4.0K Sep 22 09:51  AllPodlogs
-rw-r--r-- 1 root root 4.1K Sep 22 09:57  getall_status_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root  671 Sep 22 09:57  rs_status_all_namespaces.log
-rw-r--r-- 1 root root 2.0K Sep 22 09:57  pods_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root 6.4K Sep 22 09:57  events_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root 2.8K Sep 22 09:57  secrets_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root  748 Sep 22 09:57  svc_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root  289 Sep 22 09:57  pvc_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root  722 Sep 22 09:57  ingress_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root  305 Sep 22 09:58  cronjobs_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root  46K Sep 22 09:58  scheduler_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root 527K Sep 22 09:58  worker_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root 685K Sep 22 09:58  webserverastronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root 2.0K Sep 22 09:58 'triggerer astronomer-transparent-terminator-3163.log'
-rw-r--r-- 1 root root  17K Sep 22 09:58 'pgbouncer _astronomer-transparent-terminator-3163.log'
-rw-r--r-- 1 root root 3.1K Sep 22 09:58 'flower _astronomer-transparent-terminator-3163.log'
-rw-r--r-- 1 root root  568 Sep 22 09:58  statsd_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root 1.6K Sep 22 09:58  redis_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root  172 Sep 22 09:58  helm_history_transparent-terminator-3163.yaml
-rw-r--r-- 1 root root  19K Sep 22 09:58  helm_values_transparent-terminator-3163.yaml
/tmp/astro_logs/astronomer:
total 30M
drwxr-xr-x 2 root root  12K Sep 22 09:49 AllPodlogs
-rw-r--r-- 1 root root 5.8K Sep 22 09:53 DESCRIBE_ip-10-234-1-104.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 5.1K Sep 22 09:53 DESCRIBE_ip-10-234-1-159.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 5.8K Sep 22 09:53 DESCRIBE_ip-10-234-1-239.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 5.3K Sep 22 09:53 DESCRIBE_ip-10-234-1-242.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 5.8K Sep 22 09:53 DESCRIBE_ip-10-234-1-246.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 5.9K Sep 22 09:53 DESCRIBE_ip-10-234-2-100.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 5.6K Sep 22 09:53 DESCRIBE_ip-10-234-2-153.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 6.6K Sep 22 09:54 DESCRIBE_ip-10-234-2-22.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 6.2K Sep 22 09:54 DESCRIBE_ip-10-234-2-242.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 5.2K Sep 22 09:54 DESCRIBE_ip-10-234-2-44.us-east-2.compute.internal.log
-rw-r--r-- 1 root root 3.7M Sep 22 09:54 houstonastronomer.log
-rw-r--r-- 1 root root  20K Sep 22 09:54 houston-workerastronomer.log
-rw-r--r-- 1 root root 3.4M Sep 22 09:54 astro-uiastronomer.log
-rw-r--r-- 1 root root 3.1M Sep 22 09:54 commanderastronomer.log
-rw-r--r-- 1 root root 1.9M Sep 22 09:54 nginx_astronomer.log
-rw-r--r-- 1 root root 1.7K Sep 22 09:54 kube-state_astronomer.log
-rw-r--r-- 1 root root 3.7M Sep 22 09:54 kibana_astronomer.log
-rw-r--r-- 1 root root 1.8M Sep 22 09:54 nginx-default-backend_astronomer.log
-rw-r--r-- 1 root root  79K Sep 22 09:54 grafana_astronomer.log
-rw-r--r-- 1 root root 6.2M Sep 22 09:54 elasticsearch-nginx_astronomer.log
-rw-r--r-- 1 root root 1.7M Sep 22 09:54 cli-install_astronomer.log
-rw-r--r-- 1 root root  63K Sep 22 09:55 elasticsearch-clientastronomer.log
-rw-r--r-- 1 root root  36K Sep 22 09:55 elasticsearch-master_astronomer.log
-rw-r--r-- 1 root root  35K Sep 22 09:55 elasticsearch-data_astronomer.log
-rw-r--r-- 1 root root 175K Sep 22 09:55 stan_contatiner_astronomer.log
-rw-r--r-- 1 root root 3.2M Sep 22 09:55 registryastronomer.log
-rw-r--r-- 1 root root  38K Sep 22 09:55 prometheus_container_astronomer.log
-rw-r--r-- 1 root root 3.2K Sep 22 09:55 nats_astronomer.log
-rw-r--r-- 1 root root 1.4K Sep 22 09:55 alertmanager_astronomer.log
-rw-r--r-- 1 root root  51K Sep 22 09:55 getall_status_astronomer.log
-rw-r--r-- 1 root root 4.3K Sep 22 09:55 rs_status_all_namespaces.log
-rw-r--r-- 1 root root  12K Sep 22 09:55 pods_astronomer.log
-rw-r--r-- 1 root root 1.6K Sep 22 09:55 events_astronomer.log
-rw-r--r-- 1 root root 2.9K Sep 22 09:55 secrets_astronomer.log
-rw-r--r-- 1 root root 2.1K Sep 22 09:56 nodes.log
-rw-r--r-- 1 root root 3.3K Sep 22 09:56 kube-system.log
-rw-r--r-- 1 root root 4.4K Sep 22 09:56 svc_astronomer.log
-rw-r--r-- 1 root root 1.7K Sep 22 09:56 pvc_astronomer.log
-rw-r--r-- 1 root root 1.6K Sep 22 09:56 ingress_astronomer.log
-rw-r--r-- 1 root root  658 Sep 22 09:56 cronjobs_astronomer.log
-rw-r--r-- 1 root root 1.7K Sep 22 09:56 jobs_astronomer.log
-rw-r--r-- 1 root root  873 Sep 22 09:56 Enviornment_Info.log
-rw-r--r-- 1 root root  880 Sep 22 09:56 helm_status.log
-rw-r--r-- 1 root root 1012 Sep 22 09:56 helm_history_astronomer.log
-rw-r--r-- 1 root root  579 Sep 22 09:56 helm_values_astronomer.yaml

/tmp/astro_logs/astronomer-extraterrestrial-meteorite-6103:
total 11M
-rw-r--r-- 1 root root 9.8K Sep 22 09:43  extraterrestrial-meteorite-6103-triggerer-5f8fd74c55-cj67f-BAD_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root 9.6K Sep 22 09:43  extraterrestrial-meteorite-6103-worker-66656bd878-5vl5b-BAD_astronomer-extraterrestrial-meteorite-6103.log
drwxr-xr-x 2 root root 4.0K Sep 22 09:50  AllPodlogs
-rw-r--r-- 1 root root 4.9K Sep 22 09:56  getall_status_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root  879 Sep 22 09:56  rs_status_all_namespaces.log
-rw-r--r-- 1 root root 2.6K Sep 22 09:56  pods_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root 7.0K Sep 22 09:56  events_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root 2.8K Sep 22 09:56  secrets_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root  783 Sep 22 09:56  svc_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root  297 Sep 22 09:56  pvc_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root  746 Sep 22 09:56  ingress_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root  322 Sep 22 09:56  cronjobs_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root 1.1M Sep 22 09:56  scheduler_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root 4.9M Sep 22 09:57  worker_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root 4.3M Sep 22 09:57  webserverastronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root 3.1K Sep 22 09:57 'triggerer astronomer-extraterrestrial-meteorite-6103.log'
-rw-r--r-- 1 root root 396K Sep 22 09:57 'pgbouncer _astronomer-extraterrestrial-meteorite-6103.log'
-rw-r--r-- 1 root root 3.1K Sep 22 09:57 'flower _astronomer-extraterrestrial-meteorite-6103.log'
-rw-r--r-- 1 root root  568 Sep 22 09:57  statsd_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root  26K Sep 22 09:57  redis_astronomer-extraterrestrial-meteorite-6103.log
-rw-r--r-- 1 root root  172 Sep 22 09:57  helm_history_extraterrestrial-meteorite-6103.yaml
-rw-r--r-- 1 root root  19K Sep 22 09:57  helm_values_extraterrestrial-meteorite-6103.yaml

/tmp/astro_logs/astronomer-transparent-terminator-3163:
total 1.4M
drwxr-xr-x 2 root root 4.0K Sep 22 09:51  AllPodlogs
-rw-r--r-- 1 root root 4.1K Sep 22 09:57  getall_status_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root  671 Sep 22 09:57  rs_status_all_namespaces.log
-rw-r--r-- 1 root root 2.0K Sep 22 09:57  pods_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root 6.4K Sep 22 09:57  events_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root 2.8K Sep 22 09:57  secrets_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root  748 Sep 22 09:57  svc_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root  289 Sep 22 09:57  pvc_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root  722 Sep 22 09:57  ingress_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root  305 Sep 22 09:58  cronjobs_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root  46K Sep 22 09:58  scheduler_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root 527K Sep 22 09:58  worker_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root 685K Sep 22 09:58  webserverastronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root 2.0K Sep 22 09:58 'triggerer astronomer-transparent-terminator-3163.log'
-rw-r--r-- 1 root root  17K Sep 22 09:58 'pgbouncer _astronomer-transparent-terminator-3163.log'
-rw-r--r-- 1 root root 3.1K Sep 22 09:58 'flower _astronomer-transparent-terminator-3163.log'
-rw-r--r-- 1 root root  568 Sep 22 09:58  statsd_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root 1.6K Sep 22 09:58  redis_astronomer-transparent-terminator-3163.log
-rw-r--r-- 1 root root  172 Sep 22 09:58  helm_history_transparent-terminator-3163.yaml
-rw-r--r-- 1 root root  19K Sep 22 09:58  helm_values_transparent-terminator-3163.yaml
total 4.0K
drwxrwxrwx 10 root root 4.0K Sep 22 09:59 astro_logs
Please attach the zip file or .gz file created in /tmp to the zendesk ticket for reference.
``` 
