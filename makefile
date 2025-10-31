.PHONY: run_port_forward run_deploy run_testes run_all_failures run_graficos run_simulation run_deploy_clean

run_port_forward:
	cd Kubernetes-Clusters && nohup ./scripts/deploy.sh --port-forwards > port_forward.log 2>&1 &
	rm -f Kubernetes-Clusters/port_forward.log

run_deploy_clean:
	kubectl config delete-context local-k8s 2>/dev/null || true
	kubectl config delete-context kind-local-k8s 2>/dev/null || true
	cd Kubernetes-Clusters && ./scripts/deploy.sh --clean
# 	sleep 30
	cd Kubernetes-Clusters && ./scripts/deploy.sh --local --setup
	cd Kubernetes-Clusters && ./scripts/deploy.sh --local --deploy --ubuntu

run_deploy:
	cd Kubernetes-Clusters && ./scripts/deploy.sh --local --setup
	cd Kubernetes-Clusters && ./scripts/deploy.sh --local --deploy --ubuntu
# 	cd Kubernetes-Clusters && nohup ./scripts/deploy.sh --port-forwards > port_forward.log 2>&1 &
# 	rm -f Kubernetes-Clusters/port_forward.log

run_testes_site:
	./Kubernetes-Clusters/scripts/quick_test.sh

# 🧪 Teste isolado para verificar se o sistema de testes está funcionando
run_test_isolated:
	@echo "🧪 Iniciando teste isolado para worker node shutdown..."
	@echo "📋 Verificando nodes disponíveis..."
	kubectl get nodes | grep worker
	@echo ""
	@echo "🔌 Executando teste de shutdown de worker node..."
	cd testes && python3 reliability_tester.py --component worker_node --failure-method shutdown_worker_node --target local-k8s-worker2 --iterations 1 --interval 5
	@echo "✅ Teste isolado finalizado!"

# 🎯 Executa TODOS os métodos de falha com 30 iterações e 10s de intervalo
run_all_failures:
	@echo "🚀 Iniciando suite completa de testes de confiabilidade..."
	@echo "📊 Parâmetros: 30 iterações, 10 segundos de intervalo"
	@echo ""
	@echo "📦 ===== TESTES DE PODS ====="
	cd testes && python3 reliability_tester.py --component pod --failure-method kill_processes --target bar-app-6f7b574d56-82dnd --iterations 5 --interval 10
	@echo ""
# 	cd testes && python3 reliability_tester.py --component pod --failure-method kill_init --target test-app-86f66d945f-vvnpf --iterations 40 --interval 10
# 	@echo ""
# 	@echo "🖥️  ===== TESTES DE WORKER NODES ====="
# 	cd testes && python3 reliability_tester.py --component worker_node --failure-method kill_worker_node_processes --target local-k8s-worker --iterations 40 --interval 10
# 	@echo ""
# 	cd testes && python3 reliability_tester.py --component worker_node --failure-method kill_kubelet --target local-k8s-worker2 --iterations 40 --interval 10
# 	@echo ""
# 	cd testes && python3 reliability_tester.py --component worker_node --failure-method delete_kube_proxy --target local-k8s-worker --iterations 40 --interval 10
# 	@echo ""
# 	cd testes && python3 reliability_tester.py --component worker_node --failure-method restart_containerd --target local-k8s-worker2 --iterations 40 --interval 10
# 	@echo ""
# 	@echo "🎛️  ===== TESTES DE CONTROL PLANE ====="
# 	cd testes && python3 reliability_tester.py --component control_plane --failure-method kill_control_plane_processes --target local-k8s-control-plane --iterations 40 --interval 10
# 	@echo ""
# 	cd testes && python3 reliability_tester.py --component control_plane --failure-method kill_kube_apiserver --target local-k8s-control-plane --iterations 40 --interval 10
# 	@echo ""
# 	cd testes && python3 reliability_tester.py --component control_plane --failure-method kill_kube_controller_manager --target local-k8s-control-plane --iterations 40 --interval 10
# 	@echo ""
# 	cd testes && python3 reliability_tester.py --component control_plane --failure-method kill_kube_scheduler --target local-k8s-control-plane --iterations 40 --interval 10
# 	@echo ""
# 	cd testes && python3 reliability_tester.py --component control_plane --failure-method kill_etcd --target local-k8s-control-plane --iterations 40 --interval 10 --timeout extended
# 	@echo ""
	@echo "✅ Suite completa de testes finalizada!"
	@echo "📁 Resultados salvos em: testes/2025/10/15/component/"

run_graficos:
	cd show_graficos && python3 graficos.py

run_simulation:
# 	source ~/venvs/py3env/bin/activate && 
	cd ./testes && python3 -m kuber_bomber.cli.availability_cli --duration 1000 --iterations 5 --use-config-simples