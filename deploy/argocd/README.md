# Argo CD deployment

Install Argo CD and External Secrets through your platform bootstrap, then replace the repository URL and apply:

```bash
kubectl apply -f deploy/argocd/project.yaml
kubectl apply -f deploy/argocd/application-production.yaml
```

Argo CD runs API and AI migrations as `PreSync` hooks. A failed migration stops rollout. Workloads use automated reconciliation, pruning, self-healing, server-side apply, immutable release tags, and retain ten application revisions for rollback. HPA-owned replica fields are ignored deliberately.

Production promotion changes only `global.imageTag` in `values-production.yaml` through a reviewed pull request or the protected deployment workflow. Do not point production at mutable `latest` tags.
