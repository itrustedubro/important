FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    ffmpeg \
    libffi-dev \
    libssl-dev \
    wget \
    libicu-dev \
    apt-transport-https \
    ca-certificates \
    gpg \
    fuse \
    openvpn \
    mediainfo \
    mkvtoolnix \
    mkvtoolnix-gui \
 && rm -rf /var/lib/apt/lists/*

# Install rclone
RUN curl https://rclone.org/install.sh | bash

# Install Geckodriver
RUN wget https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-linux64.tar.gz \
 && tar -xvzf geckodriver-v0.35.0-linux64.tar.gz \
 && mv geckodriver /usr/local/bin/ \
 && rm geckodriver-v0.35.0-linux64.tar.gz

# Copy mp4decrypt and set permissions
COPY mp4decrypt /usr/local/bin/mp4decrypt
RUN chmod +x /usr/local/bin/mp4decrypt

# Download and install N_m3u8DL-RE
RUN curl -L https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.3.0-beta/N_m3u8DL-RE_v0.3.0-beta_linux-x64_20241203.tar.gz \
 | tar xz \
 && chmod +x N_m3u8DL-RE \
 && mv N_m3u8DL-RE /usr/local/bin/

# Install Shaka Packager and MPD Generator
RUN wget https://github.com/shaka-project/shaka-packager/releases/download/v3.4.2/packager-linux-x64 \
 && chmod +x packager-linux-x64 \
 && mv packager-linux-x64 /usr/local/bin/

RUN wget https://github.com/shaka-project/shaka-packager/releases/download/v3.4.2/mpd_generator-linux-x64 \
 && chmod +x mpd_generator-linux-x64 \
 && mv mpd_generator-linux-x64 /usr/local/bin/

# Install Python dependencies
RUN pip install --no-cache-dir \
    motor \
    pyplayready \
    pywidevine \
    opencv-python \
    tgcrypto \
    aiofiles \
    pyrofork \
    hachoir \
    yt_dlp \
    pytz \
    pyjwt \
    aiohttp \
    uvloop \
    pymongo \
    flask \
    brotli \
    cryptography \
    selenium \
    cloudscraper \
    requests \
    telegraph \
    asyncio \
    pycryptodome \
    bs4 \
    mediainfo \
    qbittorrent

# Copy all app files
COPY . .

# Setup rclone config
RUN mkdir -p /root/.config/rclone \
 && cp /app/rclone.conf /root/.config/rclone/rclone.conf

# Ensure app permissions
RUN chmod -R 777 /app

CMD ["python", "main.py"]
