FROM python:3

COPY . /app
WORKDIR /app
ARG CEPH_REPO_URL=https://download.ceph.com/debian-nautilus/
RUN wget -q -O- 'https://download.ceph.com/keys/release.asc' | apt-key add -
RUN true && \
  apt-add-repository "deb ${CEPH_REPO_URL} xenial main" && \
  apt-get update && \
  apt-get install -y ceph libcephfs-dev librados-dev librbd-dev curl gcc g++
EXPOSE 5000
CMD /bin/bash

