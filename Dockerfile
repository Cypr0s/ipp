### podman

#check stage 
FROM python:3.14-slim as check

#install php
RUN apt-get update && apt-get install -y php

# move dev requirements into image
COPY ./int/requirements-dev.txt /tools/

# move composer files into image
COPY ./tester/composer.phar /tools/
COPY ./tester/composer.json /tools/
COPY ./tester/composer.lock /tools/

WORKDIR /tools

# instlal python dev dependencies
RUN pip install -r ./requirements-dev.txt 

#install php dev dependencies
RUN php composer.phar install

#commands in bash
ENTRYPOINT ["/bin/bash"]


#build stage useless??
FROM python:3.14-slim AS build

# copy SRC files
COPY ./int/src/ /int/src/

#copy interpreter reqiurements
COPY ./int/requirements.txt /int/

#install dependencies
RUN pip install -r /int/requirements.txt

#runtime stage
FROM python:3.14-slim AS runtime

COPY --from=build /int/ /int/

#run interpreter entry point
ENTRYPOINT ["python3", "/int/src/solint.py" ]


#test stage
FROM runtime AS test

# install php 8.5
#RUN apt-get update && apt-get install -y lsb-release ca-certificates curl && \
#    curl -sSLo /tmp/debsuryorg-archive-keyring.deb https://packages.sury.org/debsuryorg-archive-keyring.deb && \
#    dpkg -i /tmp/debsuryorg-archive-keyring.deb && \
#    tee /etc/apt/sources.list.d/php.sources <<EOF
 
RUN apt update && apt install -y php8.5

# move tester files into image
COPY ./tester/ /tester/src

#intall php dependencies 
RUN php composer.phar install --no-dev

ENTRYPOINT [ "php", "/tester/src/tester.php" ]