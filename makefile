.PHONY: run_port_forward run_deploy run_testes run_all_failures

run_port_forward:
	cd Kubernetes-Clusters && nohup ./scripts/deploy.sh --port-forwards > port_forward.log 2>&1 &
	rm -f Kubernetes-Clusters/port_forward.log

run_deploy_clean:
	kubectl config delete-context local-k8s 2>/dev/null || true
	kubectl config delete-context kind-local-k8s 2>/dev/null || true
	cd Kubernetes-Clusters && ./scripts/deploy.sh --clean
	cd Kubernetes-Clusters && ./scripts/deploy.sh --local --deploy --ubuntu

run_deploy:
	cd Kubernetes-Clusters && ./scripts/deploy.sh --local --setup
	cd Kubernetes-Clusters && bash src/scripts/local_setup.sh
	cd Kubernetes-Clusters && ./scripts/deploy.sh --local --deploy --ubuntu
# 	cd Kubernetes-Clusters && nohup ./scripts/deploy.sh --port-forwards > port_forward.log 2>&1 &
# 	rm -f Kubernetes-Clusters/port_forward.log

run_testes_site:
	./Kubernetes-Clusters/scripts/quick_test.sh

# 🎯 Executa TODOS os métodos de falha com 30 iterações e 10s de intervalo
run_all_failures:
	@echo "🚀 Iniciando suite completa de testes de confiabilidade..."
	@echo "📊 Parâmetros: 30 iterações, 10 segundos de intervalo"
	@echo ""
# 	@echo "📦 ===== TESTES DE PODS ====="
# 	cd testes && python3 reliability_tester.py --component pod --failure-method kill_processes --target bar-app-6495f959f6-wktz9 --iterations 40 --interval 10
# 	@echo ""
# 	cd testes && python3 reliability_tester.py --component pod --failure-method kill_init --target foo-app-6898f5b49f-76c97 --iterations 40 --interval 10
# 	@echo ""
# 	cd testes && python3 reliability_tester.py --component pod --failure-method delete_pod --target bar-app-6495f959f6-wktz9 --iterations 40 --interval 10
	@echo ""
	@echo "🖥️  ===== TESTES DE WORKER NODES ====="
	cd testes && python3 reliability_tester.py --component worker_node --failure-method kill_worker_node_processes --target local-k8s-worker --iterations 40 --interval 10
# 	@echo ""
# 	cd testes && python3 reliability_tester.py --component worker_node --failure-method kill_kubelet --target local-k8s-worker --iterations 40 --interval 10
# 	@echo ""
# 	cd testes && python3 reliability_tester.py --component worker_node --failure-method delete_kube_proxy --target local-k8s-worker --iterations 40 --interval 10
	@echo ""
	cd testes && python3 reliability_tester.py --component worker_node --failure-method restart_containerd --target local-k8s-worker --iterations 40 --interval 10
	@echo ""
	@echo "🎛️  ===== TESTES DE CONTROL PLANE ====="
	cd testes && python3 reliability_tester.py --component control_plane --failure-method kill_control_plane_processes --target local-k8s-control-plane --iterations 40 --interval 10
	@echo ""
	cd testes && python3 reliability_tester.py --component control_plane --failure-method kill_kube_apiserver --target local-k8s-control-plane --iterations 40 --interval 10
	@echo ""
	cd testes && python3 reliability_tester.py --component control_plane --failure-method kill_kube_controller_manager --target local-k8s-control-plane --iterations 40 --interval 10
	@echo ""
	cd testes && python3 reliability_tester.py --component control_plane --failure-method kill_kube_scheduler --target local-k8s-control-plane --iterations 40 --interval 10
	@echo ""
	cd testes && python3 reliability_tester.py --component control_plane --failure-method kill_etcd --target local-k8s-control-plane --iterations 40 --interval 10 --timeout extended
	@echo ""
	@echo "✅ Suite completa de testes finalizada!"
	@echo "📁 Resultados salvos em: testes/2025/10/15/component/"