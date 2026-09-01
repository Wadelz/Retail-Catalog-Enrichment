# Docker Deployment Guide

This guide explains how to deploy the Catalog Enrichment application using Docker and Docker Compose.

## Architecture

The application consists of the following services:

- **Backend** (Port 8000): FastAPI backend for orchestrating enrichment workflows
- **Nemotron 3.5 Lightning LLM NIM** (Port 8002): Large Language Model for text generation
- **Embeddings NIM** (Port 8005): Embeddings for policy and manual retrieval
- **Milvus Stack** (Ports 19530, 9091, 9001): Persistent vector search for loaded policy PDFs
- **External Search API**: Exa is used by the product web insights agent

## Prerequisites

- Docker 24.0+ with Docker Compose
- NVIDIA GPU with Docker GPU support (nvidia-docker2); 2 GPUs for the default assignment below
- NVIDIA NGC API Key
- Optional Exa API Key (for product web insights)
- 200GB disk space

## Setup

### 1. Environment Variables

Create a `.env` file in the project root:

```bash
# NVIDIA NGC API Key (required for all NIM services)
NGC_API_KEY=your_ngc_api_key_here

# Exa API Key (optional; without it, /research/product-insights returns status "disabled")
EXA_API_KEY=your_exa_api_key_here
```

### 2. Create Cache Directory

```bash
export LOCAL_NIM_CACHE=~/.cache/nim
mkdir -p "$LOCAL_NIM_CACHE"
chmod a+w "$LOCAL_NIM_CACHE"
```

### 3. Create Shared Docker Network

```bash
docker network create catalog-network || true
```

## Running the Application

### Start All Services

```bash
docker-compose up -d
docker compose -f docker-compose.rag.yml up -d
```

### Start Specific Services

```bash
# Start only the backend (without NIM models)
docker-compose up -d backend

# Start a specific NIM model
docker-compose up -d llm-nim

# Start all NIM models
docker-compose up -d llm-nim embedqa

# Start the persistent policy RAG stack
docker compose -f docker-compose.rag.yml up -d
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker compose -f docker-compose.rag.yml logs -f milvus-standalone
```

### Stop Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes
docker-compose down -v
docker compose -f docker-compose.rag.yml down -v
```

## Building Images

### Build Backend

```bash
docker build -f src/backend/Dockerfile -t catalog-enrichment-backend .
```

### Rebuild All Services

```bash
docker-compose build
docker-compose up -d
```

## Accessing the Application

Once all services are running:

- **Backend API**: http://localhost:8000
- **Interactive API docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **Milvus gRPC**: localhost:19530
- **Milvus health**: localhost:9091
- **MinIO Console**: http://localhost:9001

## GPU Configuration

The default configuration assigns one GPU to each NIM model:

- Nemotron 3.5 Lightning LLM: GPU 0
- Embeddings (nv-embedqa-e5-v5): GPU 1

To adjust GPU assignments, edit the `device_ids` in `docker-compose.yml`:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          device_ids: ['0', '1']  # Use multiple GPUs
          capabilities: [gpu]
```

## Troubleshooting

### Check GPU Availability

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### Check Service Status

```bash
docker-compose ps
```

### Inspect Service Logs

```bash
docker-compose logs backend
docker-compose logs llm-nim
docker compose -f docker-compose.rag.yml logs milvus-standalone
```

### Restart a Service

```bash
docker-compose restart backend
```

### Remove and Rebuild

```bash
docker-compose down
docker-compose build --no-cache backend
docker-compose up -d
```

## Cleanup

### Remove All Containers and Images

```bash
docker-compose down --rmi all
docker compose -f docker-compose.rag.yml down -v
```

### Clean Up Cache

```bash
rm -rf ~/.cache/nim/*
```
