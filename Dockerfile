# Gunakan base image Python berbasis Linux
FROM python:3.10-slim

# Set environment variables untuk menghindari buffer output
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install package untuk set zona waktu
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    build-essential \
    libmariadb-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Set zona waktu ke Asia/Jakarta
ENV TZ=Asia/Jakarta

# Buat direktori aplikasi di dalam container
WORKDIR /app

# Salin file requirements.txt ke dalam container
COPY requirements.txt /app/

# Install dependencies Python yang diperlukan
RUN pip install --no-cache-dir -r requirements.txt

# Salin seluruh file proyek ke dalam container
COPY . /app/

# Menyebutkan direktori logs di dalam container
VOLUME ["/app/logs"]

# Ekspos port aplikasi Flask (ubah jika aplikasi Anda menggunakan port lain)
EXPOSE 8100

# Jalankan aplikasi menggunakan Gunicorn
CMD ["python", "app.py"]
