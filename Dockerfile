FROM alpine:3.19
RUN apk update && \
    apk add --no-cache \ 
    sagemath pari-gp maxima-sage-share python3-lzo
WORKDIR /opt
RUN git clone https://github.com/daedalus/oeis_closed_form_miner.git
WORKDIR /opt/oeis_closed_form_miner
RUN pip install -r "requirements.txt"
RUN git submodule init && git submodule update --remote
ENTRYPOINT ["/opt/oeis_closed_form_miner/miner.py"]
