### podman
# Dockerfile
# IPP project 2026
# Author: Kristian Luptak

#------------------check--------------------

FROM python:3.14-slim as check

# install php 8.5
RUN apt-get update && apt-get install -y lsb-release ca-certificates curl && \
    curl -sSLo /tmp/debsuryorg-archive-keyring.deb https://packages.sury.org/debsuryorg-archive-keyring.deb && \
    dpkg -i /tmp/debsuryorg-archive-keyring.deb && \
    echo "Types: deb\nURIs: https://packages.sury.org/php/\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/debsuryorg-archive-keyring.gpg" \
    > /etc/apt/sources.list.d/php.sources && \
    apt-get update && apt-get install -y php8.5 php8.5-xml

# move python dev requirements into image
COPY ./int/pyproject.toml /tools/
COPY ./int/requirements-dev.txt /tools/

# install python dev dependencies
RUN pip install --upgrade pip
RUN pip install "/tools/[dev]"
RUN pip install -r /tools/requirements-dev.txt

# commands are run `from` bash
ENTRYPOINT ["/bin/bash"]

# ------------------runtime--------------------

FROM python:3.14-slim AS runtime

# copy SRC files
COPY ./int/src/ /int/src/

# copy interpreter requirements
COPY ./int/pyproject.toml /tools/

# install dependencies
RUN pip install --upgrade pip
RUN pip install "/tools/[dev]"

#run interpreter entry point
ENTRYPOINT ["python3", "/int/src/solint.py" ]

#------------------tester--------------------

FROM runtime AS test

#composer requiremnt
RUN apt-get update && apt-get install -y git zip unzip

# install php 8.5
RUN apt-get update && apt-get install -y lsb-release ca-certificates curl && \
    curl -sSLo /tmp/debsuryorg-archive-keyring.deb https://packages.sury.org/debsuryorg-archive-keyring.deb && \
    dpkg -i /tmp/debsuryorg-archive-keyring.deb && \
    echo "Types: deb\nURIs: https://packages.sury.org/php/\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/debsuryorg-archive-keyring.gpg" \
    > /etc/apt/sources.list.d/php.sources && \
    apt-get update && apt-get install -y php8.5 php8.5-xml

# move python pip dependencies
COPY ./tester/sol2xml/requirements.txt /tools/

#install python pip dependencies
# needed for xml
RUN apt-get update && apt-get install -y libxml2-dev libxslt1-dev gcc zlib1g-dev
# pip install
RUN pip install --upgrade pip
RUN pip install -r ./tools/requirements.txt 

# copy parser into image
COPY ./tester/sol2xml/sol_to_xml.py /tester/sol2xml/
COPY ./tester/sol2xml/parser_output_schema.xsd /tester/sol2xml/

# copy tester files into image
COPY ./tester/src /tester/src/
COPY ./tester/composer.json /tester/
COPY ./tester/vendor /tester/vendor/

ENTRYPOINT [ "php", "/tester/src/tester.php" ]