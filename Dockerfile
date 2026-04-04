### podman

#------------------check------------------

FROM python:3.14-slim as check

# install php 8.5
RUN apt-get update && apt-get install -y lsb-release ca-certificates curl && \
    curl -sSLo /tmp/debsuryorg-archive-keyring.deb https://packages.sury.org/debsuryorg-archive-keyring.deb && \
    dpkg -i /tmp/debsuryorg-archive-keyring.deb && \
    echo "Types: deb\nURIs: https://packages.sury.org/php/\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/debsuryorg-archive-keyring.gpg" \
    > /etc/apt/sources.list.d/php.sources && \
    apt-get update && apt-get install -y php8.5 php8.5-xml

# move dev requirements into image
COPY ./int/pyproject.toml /tools/
COPY ./int/requirements-dev.txt /tools/

WORKDIR /tools

# instlal python dev dependencies
RUN pip install --upgrade pip
RUN pip install ".[dev]"
RUN pip install -r requirements-dev.txt

WORKDIR /

#commands in bash
ENTRYPOINT ["/bin/bash"]

#--------------build---------------------

FROM python:3.14-slim AS build

# copy SRC files
COPY ./int/src/ /int/src/

#copy interpreter reqiurements
COPY ./int/pyproject.toml /tools/

#install dependencies
WORKDIR /tools/
RUN pip install --upgrade pip
RUN pip install ".[dev]"
WORKDIR /

#--------------runtime--------------------

FROM python:3.14-slim AS runtime
# copy src
COPY --from=build /int/ /int/

#copy libs
COPY --from=build /usr/local/lib/ /usr/local/lib/

#run interpreter entry point
ENTRYPOINT ["python3", "/int/src/solint.py" ]



#-----------------test---------------------

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

# move pip dependencies
COPY ./tester/sol2xml/requirements.txt /tools/

#install python pip dependencies
RUN pip install --upgrade pip
RUN pip install -r ./tools/requirements.txt 

#copy parser into image
COPY ./tester/sol2xml/validate.py /tester/sol2xml/
COPY ./tester/sol2xml/parser_output_schema.xsd /tester/sol2xml/

# move tester files into image
COPY ./tester/src/ /tester/src/

ENTRYPOINT [ "php", "/tester/src/tester.php" ]