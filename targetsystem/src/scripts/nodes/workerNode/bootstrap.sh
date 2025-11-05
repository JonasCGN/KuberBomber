 #!/bin/bash

install_aws_cli(){
  echo "install kubectl in bucket"

  apt-get update -y
  apt-get install -y vim git curl wget zip

  curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
  unzip awscliv2.zip
  ./aws/install

}

install_aws_cli >> /var/log/bootstrap.log 2>&1