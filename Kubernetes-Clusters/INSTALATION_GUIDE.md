# Maven (3.6.3)

## Instalar sdkman

```bash
curl -s "https://get.sdkman.io" | bash
source "$HOME/.sdkman/bin/sdkman-init.sh"
```

## Instalar Maven 3.6.3

```bash
sdk install maven 3.6.3
```

```bash
mvn -version
```

# Java (jdk-22.0.1)

## Instalar JDK 22.0.1

```bash
sdk install java 22.0.1-oracle
```

## Verificar

```bash
java -version
```

# AWS CLI (2.15.40)

## Baixar e instalar

```bash
curl -L "https://awscli.amazonaws.com/awscli-exe-linux-x86_64-2.15.40.zip" -o "$HOME/Downloads/awscliv2.zip"
unzip -o "$HOME/Downloads/awscliv2.zip" -d "$HOME/Downloads"
sudo ~/Downloads/aws/install --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli --update
```

## Verificar

```bash
aws --version
```

# Node 20(Opcional caso queriqa remover o erro amarelo do cdk)

## Instalar Node 20

```bash
nvm install 20
```

## Usar Node 20

```bash
nvm use 20
```

## Definir como padrão

```bash
nvm alias default 20
```

## Verificar

```bash
node -v
npm -v
cdk --version
```

### Caso saia o cdk, instale o cdk novamente:

```bash
npm install -g aws-cdk@2.138.0
```

# AWS CDK (2.138.0 (build 6b41c8b))

## Instalar NVM (se não tiver)

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
```

## Instalar Node.js LTS

```bash
nvm install --lts
```

## Instalar AWS CDK versão fixa

```bash
npm install -g aws-cdk@2.138.0
```

## Verificar

```bash
cdk --version
```

## Instalar Docker (Linux)

As instruções abaixo cobrem as distribuições mais comuns. Prefira os passos oficiais em https://docs.docker.com/ se tiver dúvidas.

### Ubuntu / Debian (recomendado)

1. Remova versões antigas (se houver):

```bash
sudo apt-get remove -y docker docker-engine docker.io containerd runc || true
```

2. Atualize e instale dependências:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release
```

3. Adicione a chave GPG oficial do Docker e o repositório:

```bash
curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

4. Instale o Docker Engine e o plugin do compose:

```bash
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

5. Habilite e inicie o serviço:

```bash
sudo systemctl enable --now docker
```

6. (Opcional) Permita executar docker sem sudo para seu usuário:

```bash
sudo usermod -aG docker $USER
# Efetive a mudança sem logout (ou faça logout/login):
newgrp docker || true
```

7. Verifique a instalação:

```bash
docker --version
docker run --rm hello-world
```