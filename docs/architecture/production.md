# Production architecture

## Request and data flow

```mermaid
flowchart LR
  U[Patients and workforce] -->|TLS 1.2+| WAF[Cloud WAF / Load Balancer]
  WAF --> WEB[Next.js web replicas]
  WAF --> GW[FastAPI gateway replicas]
  GW --> API[Core API replicas]
  GW --> AI[AI API replicas]
  AI --> Q[(Redis Streams)]
  Q --> WORKERS[AI worker pool]
  AI --> LLM[LiteLLM gateway]
  WORKERS --> LLM
  LLM --> PROVIDERS[BAA-approved model providers]
  API --> PG[(Multi-AZ PostgreSQL + pgvector)]
  AI --> PG
  API --> REDIS[(Multi-AZ Redis)]
  GW --> REDIS
```

## Cloud and observability topology

```mermaid
flowchart TB
  subgraph AWS[Private AWS VPC across three availability zones]
    subgraph EKS[EKS private worker subnets]
      APP[HealthOS Helm release]
      ESO[External Secrets]
      PROM[Prometheus]
      GRAF[Grafana]
      OTEL[OpenTelemetry collectors]
      TEMPO[Tempo trace store]
    end
    RDS[(RDS PostgreSQL Multi-AZ)]
    EC[(ElastiCache Multi-AZ)]
    SM[Secrets Manager]
    KMS[KMS customer key]
    S3[(Object-locked compliance bucket)]
    BACKUP[AWS Backup vault]
  end
  APP --> OTEL --> TEMPO
  PROM --> APP
  GRAF --> PROM
  GRAF --> TEMPO
  ESO --> SM
  KMS --> RDS
  KMS --> EC
  KMS --> SM
  KMS --> S3
  RDS --> BACKUP
```

## Fault tolerance

- Three replicas for request-serving workloads, spread across zones and nodes.
- Rolling updates permit zero unavailable pods; PodDisruptionBudgets retain quorum during maintenance.
- HPA independently scales web, gateway, API, AI, workers, and LiteLLM.
- RDS and ElastiCache use Multi-AZ failover, private subnets, encryption, and 35-day native recovery windows.
- Redis Streams decouple synchronous APIs from AI workers and reclaim abandoned work.
- Argo CD self-heals drift and blocks rollout when migration hooks fail.

## Trust boundaries

Internet traffic terminates at a managed load balancer/WAF. Only web and gateway services accept ingress-controller traffic. API, AI, workers, and LiteLLM communicate inside default-deny network policies. Data services are reachable only from EKS node security groups over TLS; keep the Helm `networkPolicy.dataPlaneCidr` aligned with the Terraform VPC CIDR. Secrets enter pods from AWS Secrets Manager through short-scoped IRSA credentials.
