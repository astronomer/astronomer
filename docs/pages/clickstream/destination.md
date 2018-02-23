---
layout: page
hide: true
title: Create a Clickstream Destination
permalink: /clickstream/destination/
order: 1
---

## Overview

This document describes the overall process for developing a new clickstream integration on the client-side, server-side, and mobile.

### Purpose

The purpose of this document is to provide the definitive checklist for a developer to create any integration whether client-side, server-side, source, fork, etc.

## 1. Setup

1. **Create an Astronomer account**
    - Access to individual organizations can be granted by a super admin.
1. **Get access to required external services**
    - Have customer configure any required settings if we can’t modify ourselves.
    - This depends on each integration but for example, ask the customer to add our devs to their DoubleClick account in staging + prod for an enterprise-y integration.  For simpler integrations, we can make our own trial / free accounts.  If we can’t get either, we can reach out to the company and explain what we’re building to try to get special access.
    - It’d be nice to have one dev@astronomer.io account used universally but today people mostly make one offs with their personal accounts.
1. **Get access to required internal services**
    - For example, every server-side integration requires a Kafka stream to be created.  Many integrations need access to S3, RDS, Redshift, or other Amazon services.
    - Your integration may require additional downstream services as well.  Ask Ken or Will to create and grant access.
1. **Obtain credentials for required services**
    - API keys, secrets, etc.
    - Ideally all of this is in place after the scope request phase and before starting the dev work phase to reduce the number of blockers during dev time.
1. **Test service credentials**

## 2. Configuration

For fast local development, you may want to skip this section for now by starting with a hardcoded JSON config, then build out the config objects once the schema shape and design have been defined.

1. **Understand clickstream config schemas**
    - Providers, connections, clickstream configs, etc.
    - We might have a schema diagram of this somewhere.
1. **Define shape and schema of connection, config, and provider**
    - This can be more time consuming than it sounds.  We typically iterate on these during the course of development.
    - Aim for API consistency with Segment.  If the integration is a Segment fork, look at their unit tests and reverse engineer their config structure.  If the integration is a source, we encourage consistency with our other integrations — look at recent clickstreamConfigs for examples.
1. **Create connection config and clickstream config(s) in staging for testing purposes**
    - Use the web app over Mongo directly if possible to mirror a customer’s usage.  Not always possible in advanced use cases.

## 3. Development

1. **Write the code**
    - **A. Source**
        - For a new source, follow the naming conventions of similar integration repos.
        - Example: [analytics.js-integration-retention-science](https://github.com/astronomer-integrations/analytics.js-integration-retention-science)
    - **B. Fork**
        - For a forked integration repo, make code changes if expansion / modifications are required to support our use case.
        - Example: [analytics.js-integration-adwords](https://github.com/astronomer-integrations/analytics.js-integration-adwords)

1. **Run it**
    - **A. Client-side integration**
        - Client-side integrations run in the browser via analytics.js, and are simpler and easier to write but may not fit all use cases, especially if you need to send large payloads to multiple destinations.
        - Follow the design patterns used in existing integrations.
        - Enable debug mode in the browser by calling `analytics.debug();` to ease iteration during the development process.  You can also disable debug mode by calling `analytics.debug(false);`.
        - Example: [analytics.js-integration-google-analytics](https://github.com/astronomer-integrations/analytics.js-integration-google-analytics)
    - **B. Server-side integration**
        - Server-side integrations run as a service on the backend server.
        - Create an integration worker service.  If you're not using about how much CPU or memory to allocate, reference similar existing services.  This is dependent on the load each integration receives and may require some iteration on config in production.
        - Example: [integration-google-analytics](https://github.com/astronomer-integrations/integration-google-analytics)
    - **C. Mobile integration**
        - Mobile integrations run in a native app on iOS, Android, etc.  They are less common than client-side and server-side integrations.
        - Create an integration worker service.  If you're not using about how much CPU or memory to allocate, reference similar existing services.  This is dependent on the load each integration receives and may require some iteration on config in production.
        - Example: [analytics-ios-integration-facebook-app-events](https://github.com/astronomer-integrations/analytics-ios-integration-facebook-app-events)

1. **Add the integration to a new or existing app to test it**

## 4. Testing

1. **Unit testing**
    - Writing smaller functions makes this easier and eases or avoids having to refactor later.  Use mocking for service unit tests.
    - We don’t do as much automated testing today as we would like.  Most of our components are based around APIs or external services which adds complexity to unit testing.  Typically we do more manual testing.  We could benefit from creating follow up issues for this or committing time to it.
1. **Lint**
1. **Integration testing**
    - Integration testing is best performed post-deploy in the cluster environment as opposed to trying to simulate the full setup locally.

## 5. Documentation

1. **(Internal) Write one-line docstrings on major classes and functions**
    - We write some internal docs today, mostly code comments.
1. **(External) Write basic docs**
    - Ideally external docs describe: (1) how a customer sets up the service, (2) how they configure the service, (3) how they configure our app for the service.  We do some of this today but outside of the dev cycle.  Example from Segment: Amazon Kinesis Destination.

## 6. Code Review

1. **Open a PR requesting code review**
    - Include your timeline for the reviewer if urgent or high priority.  Mark the reviewer as both “assigned to” and “reviewer”.
    - If possible assign to someone who’s knowledgeable on that codebase + has availability.
    - Clarify in your PR if you're seeking a test of functionality, style, design patterns, or what the goal of your code review is.

## 7. Misc

1. **Migrate any old config data in the config database**
    - If this integration deprecated a previous version or made config variables obsolete, clean that up by migrating and removing any old configs.  Check Mongo for how many and which customers are impacted.
    - If you have time, do cleanup tasks during integration dev; otherwise, spin off as separate internal follow up issue to reduce tech debt.
1. **Add an integration icon**
    - By default, integrations will have a generic icon in the Astronomer UI.
    - To add a custom icon, add a .png file to `/src/static/destinations` in Galaxy
    - Then add an entry in the destinations array in `/src/components/Platform/icons.js`

## 8. Deployment

### A. Dev / Staging

1. **Create the service in DC/OS using JSON config**
    - Copy the template from a similar service and modify as needed.
    - Example: For a Kinesis destination, name the worker “integration-worker-kinesis”.
1. **Deploy integration in DC/OS staging**
    - We do manual integration testing on staging with the deployment.  Re-deploy as needed.
    - Some bugs can be caught on in our dev environment but we do not have a true staging environment that mirrors all services in prod.  Debugging mostly needs to happen in prod today.
1. **Test that code runs end-to-end**

### B. Prod

1. **Create connection config and clickstream config(s) in prod**
    - Use real creds if we have them; otherwise, copy configs from staging.
    - Some values like app IDs will be different in prod.
1. **Deploy integration in DC/OS prod**
    - Mostly copy the staging config but resource requirements (CPU, memory, etc) are different in prod.  Look at similar configs in prod.
1. **Test that code runs successfully end-to-end**
    - Don’t assume it will work in prod because it worked in dev.  In prod, there are edge cases and the environment is more complex, more demand on resources, etc.
1. **Performance testing**
    - Typically we solve scaling challenges by using more efficient algorithms or increasing cluster resource allocation.
