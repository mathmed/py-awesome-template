FROM python:3.10

WORKDIR /

RUN mkdir /home/app

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod 755 /usr/local/bin/entrypoint.sh && ln -s /usr/local/bin/entrypoint.sh

# To control project dependencies
RUN pip install --upgrade pip && pip install poetry

EXPOSE 80

ENTRYPOINT [ "entrypoint.sh" ]
