# Asynchronous Transaction Risk & AML Triaging Engine

A high-performance, FCA-compliant transaction triaging engine built using **FastAPI**, **CrewAI** (multi-agent orchestration), **Strawberry GraphQL**, and **Gemini 2.5**.

## System Architecture Blueprint
1. **Ingest Layer**: Parses nested ISO 20022 message streams via validation boundaries.
2. **Background Processing**: Delegates complex verification to async threads to prevent transactional locking.
3. **CrewAI Compliance Loop**: Runs three discrete agents (Sifter, OSINT, and Risk Scorer) to verify transactions.
4. **FCA Compliance Logging**: Caches audit traces in structured GraphQL frameworks for instant investigations.

## Quickstart Guide
1. Run local container setup:
   ```bash
   docker-compose up --build
   ```
2. Access the Swagger endpoint: `http://localhost:8000/docs`
3. Query audit logs via GraphQL: `http://localhost:8000/graphql`
