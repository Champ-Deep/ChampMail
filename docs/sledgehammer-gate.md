# Isolated SMTP gate

Start the core services with `CHAMPMAIL_SMTP_RELAY=mailpit:587 docker compose up -d --build backend worker postgres redis mail-engine`.

Start the development sink on that Compose network (replace `champmail` if using `-p`):

```sh
docker run -d --name champmail-gate-mailpit --network champmail_champmail-network --network-alias mailpit --network-alias smtp -p 127.0.0.1:8027:8025 -e MP_SMTP_BIND_ADDR=0.0.0.0:587 axllent/mailpit:latest
```

The `smtp` alias catches the existing Python sender's port 587 without running Postfix. Never start the `smtp` Compose service alongside this sink. Go uses the relay environment; Python uses its existing transport selection, including InboxKit mailbox rotation only for provisioned domains. No provider credentials are needed for a non-InboxKit test domain. Inspect messages at `http://127.0.0.1:8027/api/v1/messages`.

ChampGraph is no longer attached automatically. Deployments that need it must supply their own network attachment; this change only removes the external-network prerequisite, not application calls to ChampGraph.
