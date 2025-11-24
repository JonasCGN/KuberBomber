.PHONY: clear_maven run_deploy_aws run_deploy_aplication destroy_deploy_aplication \
	run_all_failures run_all_failures_aws run_graficos run_simulation \
	generate_config generate_config_aws generate_config_all generate_config_all_aws \
	install_tools_aws_pods check_aws_pods_tools setup_aws_pods_complete \
	build_enhanced_image install_tools_current_pods check_pods_tools \
	update_deployments_enhanced deploy_enhanced_setup ssh_cli_cp ssh_cli_wn

run_deploy_aws:
	cd targetsystem &&  cdk bootstrap --template my-bootstrap-template.yaml

run_deploy_aplication:
	cd targetsystem &&  cdk deploy --require-approval never

# install_debug_tools
# 	ssh -i ~/.ssh/vockey.pem ubuntu@13.220.247.218 "sudo kubectl apply -f - << 'EOF'
# 	$(cat /mnt/Jonas/Projetos/Artigos/1_Artigo/targetsystem/src/scripts/nodes/controlPlane/kubernetes/kub_deployment.yaml)
# 	EOF"

destroy_deploy_aplication:
	cd targetsystem &&  cdk destroy -f

clear_maven:
	cd targetsystem && mvn clean install

# 🎯 Executa TODOS os métodos de falha com 30 iterações e 10s de intervalo
run_all_failures:
	@echo "🚀 Iniciando suite completa de testes de confiabilidade..."
	@echo "📊 Parâmetros: 30 iterações, 10 segundos de intervalo"
	@echo ""
# 	@echo "📦 ===== TESTES DE PODS ====="
# 	cd kuber_bomber && python3 reliability_tester.py --component pod --failure-method kill_processes --target bar-app-6f7b574d56-82dnd --iterations 5 --interval 10
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component pod --failure-method kill_init --target test-app-86f66d945f-vvnpf --iterations 40 --interval 10
# 	@echo ""
# 	@echo "🖥️  ===== TESTES DE WORKER NODES ====="
# 	cd kuber_bomber && python3 reliability_tester.py --component worker_node --failure-method kill_worker_node_processes --target local-k8s-worker --iterations 40 --interval 10
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component worker_node --failure-method kill_kubelet --target local-k8s-worker2 --iterations 40 --interval 10
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component worker_node --failure-method delete_kube_proxy --target local-k8s-worker --iterations 40 --interval 10
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component worker_node --failure-method restart_containerd --target local-k8s-worker2 --iterations 40 --interval 10
# 	@echo ""
# 	@echo "🎛️  ===== TESTES DE CONTROL PLANE ====="
# 	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_control_plane_processes --target local-k8s-control-plane --iterations 40 --interval 10
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_kube_apiserver --target local-k8s-control-plane --iterations 40 --interval 10
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_kube_controller_manager --target local-k8s-control-plane --iterations 40 --interval 10
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_kube_scheduler --target local-k8s-control-plane --iterations 40 --interval 10
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_etcd --target local-k8s-control-plane --iterations 40 --interval 10 --timeout extended
# 	@echo ""
# 	@echo "✅ Suite completa de testes finalizada!"
# 	@echo "📁 Resultados salvos em: testes/2025/10/15/component/"

# 🎯 Executa TODOS os métodos de falha AWS com 5 iterações 
run_all_failures_aws:
	@echo ""
	@echo "📦 ===== TESTES DE PODS AWS ====="
# 	cd kuber_bomber && python3 reliability_tester.py --component pod --failure-method kill_processes --target bar-app-df9db64d6-bh55z --iterations 1 --interval 5 --aws
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component pod --failure-method kill_init --target foo-app-86d576dd47-5w6s2 --iterations 1 --interval 5 --aws
# 	@echo ""
# 	@echo "🖥️  ===== TESTES DE WORKER NODES AWS ====="
# 	cd kuber_bomber && python3 reliability_tester.py --component worker_node --failure-method shutdown_worker_node --target ip-10-0-0-10 --iterations 1 --interval 10 --aws
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component worker_node --failure-method kill_kubelet --target ip-10-0-0-10 --iterations 1 --interval 1 --aws
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component worker_node --failure-method delete_kube_proxy --target ip-10-0-0-10 --iterations 1 --interval 10 --aws
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component worker_node --failure-method restart_containerd --target ip-10-0-0-10  --iterations 1 --interval 10 --aws
# 	@echo ""
# 	@echo "🎛️  ===== TESTES DE CONTROL PLANE AWS ====="
# 	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_control_plane_processes --target ip-10-0-0-219 --iterations 10 --interval 5 --aws
# 	@echo ""
	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method shutdown_control_plane --target ip-10-0-0-219 --iterations 1 --interval 5 --aws
	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_kube_apiserver --target ip-10-0-0-219 --iterations 1 --interval 5 --aws
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_kube_controller_manager --target ip-10-0-0-219 --iterations 1 --interval 5 --aws
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_kube_scheduler --target ip-10-0-0-219 --iterations 1 --interval 1 --aws
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_etcd --target ip-10-0-0-219 --iterations 1 --interval 5 --aws --timeout extended
# 	@echo ""
# 	@echo "✅ Suite completa de testes AWS finalizada!"
# 	@echo "📁 Resultados salvos em: testes/2025/11/04/component/"

install_requirements:
	cd kuber_bomber && pip install -r requirements.txt

run_graficos:
	cd show_graficos && python3 graficos.py

run_simulation:
# 	source ~/venvs/py3env/bin/activate && 
	cd ./ && python3 -m kuber_bomber.cli.availability_cli --use-config-simples

run_simulation_aws:
# 	source ~/venvs/py3env/bin/activate && 
	cd ./ && python3 -m kuber_bomber.cli.availability_cli --use-config-simples --force-aws

generate_config:
# 	source ~/venvs/py3env/bin/activate && 
	cd ./ && python3 -m kuber_bomber.cli.availability_cli --get-config

generate_config_aws:
# 	source ~/venvs/py3env/bin/activate && 
	cd ./ && python3 -m kuber_bomber.cli.availability_cli --get-config --force-aws

generate_config_all:
# 	source ~/venvs/py3env/bin/activate && 
	cd ./ && python3 -m kuber_bomber.cli.availability_cli --get-config-all

generate_config_all_aws:
# 	source ~/venvs/py3env/bin/activate && 
	cd ./ && python3 -m kuber_bomber.cli.availability_cli --get-config-all --force-aws

ssh_cli_cp:
	ssh -i ~/.ssh/vockey.pem ubuntu@44.204.216.190

ssh_cli_wn:
	ssh -i ~/.ssh/vockey.pem ubuntu@13.220.170.35

# 🛠️ INSTALAR FERRAMENTAS NOS PODS AWS (VIA SSH)
install_tools_aws_pods:
	@echo "🛠️ Instalando ferramentas nos pods AWS via SSH..."
	@echo "📦 Conectando em 3.80.142.210 e instalando procps, psmisc, curl..."
	ssh -i ~/.ssh/vockey.pem ubuntu@3.80.142.210 ' \
		for pod in $$(sudo kubectl get pods -o name | grep -E "(foo-app|bar-app|test-app)" | cut -d/ -f2); do \
			echo "📦 Instalando em $$pod..."; \
			sudo kubectl exec $$pod -- sh -c "apt update -qq && apt install -y -qq procps psmisc net-tools iputils-ping curl >/dev/null 2>&1" || echo "Erro em $$pod"; \
			echo "✅ $$pod processado"; \
		done \
	'
	@echo "✅ Instalação nos pods AWS concluída!"

# 🔍 VERIFICAR SE PODS AWS TÊM FERRAMENTAS (VIA SSH)
check_aws_pods_tools:
	@echo "🔍 Verificando ferramentas nos pods AWS..."
	ssh -i ~/.ssh/vockey.pem ubuntu@3.80.142.210 ' \
		echo "✅ VERIFICAÇÃO DE FERRAMENTAS NOS PODS"; \
		echo ""; \
		for pod in $$(sudo kubectl get pods -o name | grep -E "(foo-app|bar-app|test-app)" | cut -d/ -f2); do \
			echo "=== $$pod ==="; \
			sudo kubectl exec $$pod -- which ps >/dev/null 2>&1 && echo "✅ ps: OK" || echo "❌ ps: MISSING"; \
			sudo kubectl exec $$pod -- which kill >/dev/null 2>&1 && echo "✅ kill: OK" || echo "❌ kill: MISSING"; \
			sudo kubectl exec $$pod -- which curl >/dev/null 2>&1 && echo "✅ curl: OK" || echo "❌ curl: MISSING"; \
			sudo kubectl exec $$pod -- which pgrep >/dev/null 2>&1 && echo "✅ pgrep: OK" || echo "❌ pgrep: MISSING"; \
			echo ""; \
		done; \
		echo "🎯 Verificação concluída!" \
	'

# 🔄 WORKFLOW COMPLETO AWS: INSTALAR + VERIFICAR + TESTAR
setup_aws_pods_complete:
	@echo "🚀 Iniciando setup completo dos pods AWS..."
	@echo "1️⃣ Instalando ferramentas..."
	make install_tools_aws_pods
	@echo "2️⃣ Verificando instalação..."
	make check_aws_pods_tools
	@echo "3️⃣ Testando comando kill..."
	ssh -i ~/.ssh/vockey.pem ubuntu@3.80.142.210 'sudo kubectl exec $$(sudo kubectl get pods -o name | grep bar-app | cut -d/ -f2 | head -1) -- ps aux | head -2'
	@echo "✅ Setup AWS completo finalizado! Pods prontos para Kuber Bomber."

