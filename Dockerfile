FROM python:3

COPY . /app
WORKDIR /app
RUN apt-get install librados-dev && pip install -r requirements.txt
EXPOSE 5000
CMD python ./catapult-storage.py

