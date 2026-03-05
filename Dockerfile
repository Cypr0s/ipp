### podman

#check stage
FROM python:3.14 AS check

LABEL org.opencontainers.image.authors=
# move dev requirements into image
COPY ./int/requirements-dev.txt ./src/int/

# add layer(cache it)
RUN pip install -r ./src/int/requirements-dev.txt

#commands in bash
ENTRYPOINT bash


#runtime stage
FROM python:3.14 as runtime

# copy SRC files
COPY ./int/src/* ./int/src/

#copy interpreter reqiurements
COPY ./int/requirements.txt ./int/

#install dependencies
RUN pip install -r ./int/requirements.txt

#run interpreter entry point
CMD python3 ./int/src/solint.py "$@"
