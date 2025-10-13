#!/bin/bash


after_install(){

  bucketName=$1

  apt-get install -y zip

  curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
  unzip awscliv2.zip
  ./aws/install

  echo '#!/bin/bash' > /root/start.sh
  tail -n 2 /root/addworkernode.txt >> /root/start.sh
  chmod +x /root/start.sh

  aws s3 cp /root/start.sh s3://"${bucketName}"/start.sh

}




echo "install cp" >> /var/log/after_install.log
after_install $1 >> /var/log/after_install.log

