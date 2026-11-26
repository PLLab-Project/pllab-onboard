FROM ubuntu:26.04
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      openssh-server python3 python3-jwt python3-cryptography sudo procps passwd ca-certificates >/dev/null \
 && mkdir -p /run/sshd
COPY server /src/server
RUN sh /src/server/install.sh --harden
CMD ["/usr/sbin/sshd", "-D", "-e"]
