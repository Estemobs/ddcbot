FROM python:3.14-slim

# git est nécessaire au runtime pour la fonctionnalité de changelog automatique (cogs/changelog.py)
RUN apt-get update \
    && apt-get install -y --no-install-recommends git libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch/torchvision CPU-only (index officiel PyTorch) : évite d'installer
# le stack nvidia-CUDA entier (~multi-Go) inutile pour easyocr (gpu=False),
# qui ne fait que bloat l'image et épuiser le disque.
RUN pip install --no-cache-dir torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-u", "main.py"]
