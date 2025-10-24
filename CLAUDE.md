# astronomer

this repo contains code that users use to install astro private cloud (formerly known as astronomer software).

users have their own kubernetes clusters and install the main helm chart within them.

users clusters are unique! they might be EKS, AKS, GKE, or any other cloud provider, or even on-premises or managed by openshift.

users' clusters are often maintained by other teams who have higher permissions and can configure them to have security requirements, for example gatekeeper policies, network restrictions (airgapped), and other security measures.

a typical installation command that a user/admin will run is:

```
helm upgrade --install -n astronomer -f values.yaml --version 0.37.4 --debug astronomer astronomer/astronomer
```

note: users run different versions of the chart! this repo has tags that correspond to the chart versions!

to view the code of a specific version, you can use the following command:

```
git checkout <version_tag>
```
where `version_tag` is something like `v0.37.4`.

---

your main role is to help me, Lee, understand this code base and troubleshoot issues with users' installations. if i don't specify a version, you should no make an assumption. instead, ask me what version you should use!

---

you will often need to look at upstream code to understand how the chart works and how to troubleshoot issues. you can find the upstream code at `/Users/lee.gaines/astronomer`, where I have cloned the upstream repos, such as `commander` and `houston-api`.

---

## Using Agents for Complex Tasks

**Important:** You have access to specialized agents that can help answer complex questions more effectively. You should **proactively use agents** when appropriate - don't wait for Lee to ask!

### When to Use Agents

Use agents for tasks that require:
- Deep source code analysis across multiple files or repositories
- Tracing configuration options through helm chart subcharts
- Version-specific behavior investigation
- Authoritative answers with file citations
- Complex searches that may require multiple iterations
- Documentation verification or cross-referencing

### Common Scenarios Where Agents Should Be Used

- **Configuration questions**: "Where should X go in values.yaml?" or "What's the correct setting for Y?"
  → Use `apc-source-expert` to trace through helm charts and provide definitive answers with citations

- **Dependency/version questions**: "What version of Redis/Postgres/etc is used in APC X.Y.Z?"
  → Use `apc-source-expert` to check the updates API and helm chart references

- **Troubleshooting**: Customer issues requiring analysis of how components work
  → Use `apc-source-expert` to investigate the actual code behavior

- **Documentation verification**: Checking if procedures or configurations are documented correctly
  → Use `apc-docs-expert` to reference official documentation

- **Multi-repo searches**: Finding references across commander, houston-api, and helm charts
  → Use `general-purpose` for coordinated searches

### Custom Agents

Lee may add custom agents in `.claude/agents/` for specialized tasks. Check that directory if it exists and use any relevant agents based on their descriptions.

**Remember:** Agents provide more thorough, authoritative answers with proper citations. Use them proactively when the task complexity warrants it!
