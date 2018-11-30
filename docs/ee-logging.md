---
title: "Logging"
description: "Logging in Astronomer Enterprise."
date: 2018-10-12T00:00:00.000Z
slug: "ee-logging"
menu: ["Enterprise Edition"]
position: [5]
---

In v0.8 of our platform (coming soon!), we'll pipe Airflow task logs from Elasticsearch to Airflow UI, and scheduler and web-server logs from Elasticsearch to Astronomer UI.

Here, you will find how to configure that logging setup, when it is released.

# Logging

> Capture and filter Airflow event data to a wide range of output streams. Utilize Airflow's custom logging interface and manage deployment-by-deployment logging behavior and log persistence.

#### Overview
Astronomer's Enterprise offering has a robust logging structure sitting atop Airflow. To get a better sense of how logging is structured in Airflow, check out our guide on [customizing logging in Airflow](https://www.astronomer.io/guides/logging/). We highly recommend you read through the guide if you are unfamiliar Airflow's logging, or with Python's `logging` module in general. Log output is smooth and intuitive, to make diagnosing potential Airflow failures simpler and less stressful. Logging configurations are controlled from the environment, and filtering is configured in a combined FluentD and Elasticsearch stack. Since the platform runs on top of Kubernetes, the stack has been designed to efficiently route and store large volumes of events without relying too much on stateful set persistent volumes.

***
#### Log Message Attributes
There are several configurable options that can be captured from log data. By default, the platform will capture a few key `LogRecord` attributes.

| Attribute   | Description                                                                                                           |
|-------------|-----------------------------------------------------------------------------------------------------------------------|
| `asctime`   | Time, in a human-readable format, at which the LogRecord was created.                                                 |
| `levelname` | The level of the event the LogRecord was created for. Typical log levels include `DEBUG`, `ERROR`, `INFO`, `WARNING`. |
| `filename`  | The file name from which the event was instantiated. This is taken from the `pathname`.                               |
| `lineno`    | The line number from where the logger made a call.                                                                    |
| `message`   | The actual log message detailing the event occurance.
**Important**
<span style="background-color: #09acc6">These attributes are **crucial** for the platform's Elasticsearch and FluentD stack to operate correctly, as they are used to generate a `log_id` used for looking up logs in Elasticsearch. If additional attribute output is desired, attributes can be added to the `RECORD_LABEL` list in the custom `log_config.py` file when setting up custom logging in Airflow. Additional attribute information can be found [here](https://docs.python.org/3/library/logging.html#logrecord-attributes).</span>

#### Configuring FluentD log filtering
The Enterprise platform is deployed through Helm, and there is a provided `fluentd` chart to deploy a FluentD service. The FluentD configuration will consider all log output streams, and filter out information by attributes that is specified by the `fluentd-configmap.yaml`. Raw records are grabbed indiscriminately from all running containers on the host and forwarded over a TCP port to the waiting FluentD log collection daemon running on every host. All records are filtered down by namespace and Airflow component (webserver, scheduler, or worker).

FluentD relies on a system of record tags and regex matching to keep, delete, and modify records. You can override the `filter` directives to change the behavior and flow of logs. This includes filtering out events through `grep`, enriching records with additional data or metadata, and deleting fields. The `match` directive is almost strictly used to modify log tags.

In short, you should use `match` to re-tag log events and `filter` to modify/delete the log event fields. A common pattern is to `match` log events to a new tag, and then add fields to that new tag using `filter`.

```
<match OLD_LOG_TAG.**>
  @type DESIRED_FLUENTD_PLUGIN
  <rule>
    key EXISTING_LOG_FIELD
    pattern ^(scheduler)$
    tag NEW_LOG_TAG
  </rule>
</match>
```
An example match directive configuration, similar to what you might see in the platform chart, is above.
1. The `key` specifies the field.
2. The `pattern` is another regex that specifies the desired value of the component key.
3. The `tag` is the desired new tag for the logs caught by the rule.

Any arbitrary number of rules an be written to capture logs.

```
<filter NEW_LOG_TAG.**>
  @type DESIRED_FLUENTD_PLUGIN
  format json
  replace_invalid_sequence true
  emit_invalid_record_to_error false
  key_name EXISTING_LOG_FIELD
  reserve_data true
</filter>
```
Now that we've rewritten the tag using a `match`, we can use a `filter` directive to capture and modify the newly tagged logs.
**NOTE**: Order does matter in the FluentD configuration file. Filter directives are evaluated and applied top-down, in a descending order. Therefore, it is safest to follow this with both match and filter directives to ensure expected behavior. If FluentD cannot match a tag, it will ignore it and the logs will not be allowed to pass.

At the end of the log pipeline, logs can now be redirected to a destination. Our platform is built to redirect logs to Elasticsearch, but FluentD supports a wide range of remote storage destinations, including Kafka, Mongo, and BigQuery, through its `plugins`. Find a list of all FluentD plugins [here](https://www.fluentd.org/plugins/all).

#### Logging Best Practices
* Try to separate log message data from log metadata. This includes filename, line number, and creation time as metadata. Tryng to parse and filter this information in any log pipeline can get messy, very quickly.
* Build FluentD configuration files from the top down, not only because order matters when using many of FluentD's directives, but also because it makes the config easier to modify and/or repair.
* If a FluentD filter is causing logs to go missing, but everything looks correct, check whether the correct plugin is installed for use on the daemon itself.
* Try to keep log tags as succinct as possible. Too many tags can become hard to manage, especially when the pattern matching is relient upon regular expressions.
