ARG BUILD_FROM
FROM ${BUILD_FROM}

# Instal·lem Python i paquets bàsics de compilació
RUN apt update && apt install -y \
    build-essential \
    python3 \
    python3-dev \
    python3-pip \
    dos2unix \
    libffi-dev \
    && pip install --upgrade pip

# Instal·lem llibreries Python
RUN pip install \
    requests \
    pandas \
    scikit-learn \
    psutil \
    numpy \
    holidays \
    tomli \
    func_timeout \
    schedule \
    plotly \
    colorlog \
    tzlocal \
    safe-pysha3 \
    eth-keys

# Afegim els fitxers del projecte
ADD ./rootfs/server.py .
ADD ./rootfs/bottle.py .
ADD ./rootfs/sqlDB.py .
ADD ./rootfs/logging_config.py .
ADD ./rootfs/blockchain.py .

# Forecast
COPY ./rootfs/forecast /forecast/
COPY ./rootfs/abstraction /abstraction/

# HTML, imatges i recursos
COPY ./rootfs/www /www/
COPY ./rootfs/images/ /images/
COPY ./rootfs/resources/ /resources/

# Config
COPY config.yaml config.yaml

# Script d'inici
COPY ./rootfs/run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
