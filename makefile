.PHONY: clear_maven run_deploy_aws run_deploy_aplication destroy_deploy_aplication run_all_failures run_all_failures_aws run_graficos run_simulation run_test_pode_limiter test_aws_pod_kill_processes test_aws_pod_kill_init test_aws_worker_kill_processes test_aws_worker_kill_kubelet test_aws_worker_delete_proxy test_aws_worker_restart_containerd test_aws_cp_kill_processes test_aws_cp_kill_apiserver test_aws_cp_kill_controller test_aws_cp_kill_scheduler test_aws_cp_kill_etcd test_aws_list_targets

clear_maven:
	cd targetsystem && mvn clean install

run_deploy_aws:
	cd targetsystem &&  cdk bootstrap --template my-bootstrap-template.yaml

run_deploy_aplication:
	cd targetsystem &&  cdk deploy --require-approval never

destroy_deploy_aplication:
	cd targetsystem &&  cdk destroy -f

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
# 	cd kuber_bomber && python3 reliability_tester.py --component pod --failure-method kill_processes --target bar-app-775c8885f5-6wdlt --iterations 10 --interval 5 --aws
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component pod --failure-method kill_init --target foo-app-864f66dd4d-lt8rf --iterations 10 --interval 5 --aws
# 	@echo ""
	@echo "🖥️  ===== TESTES DE WORKER NODES AWS ====="
# 	cd kuber_bomber && python3 reliability_tester.py --component worker_node --failure-method kill_worker_node_processes --target ip-10-0-0-241 --iterations 10 --interval 5 --aws
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component worker_node --failure-method kill_kubelet --target ip-10-0-0-241 --iterations 10 --interval 5 --aws
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component worker_node --failure-method delete_kube_proxy --target ip-10-0-0-241 --iterations 10 --interval 5 --aws
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component worker_node --failure-method restart_containerd --target ip-10-0-0-241 --iterations 10 --interval 5 --aws
# 	@echo ""
# 	@echo "🎛️  ===== TESTES DE CONTROL PLANE AWS ====="
	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_control_plane_processes --target ip-10-0-0-28 --iterations 10 --interval 5 --aws
	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_kube_apiserver --target ip-10-0-0-28 --iterations 10 --interval 5 --aws
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_kube_controller_manager --target ip-10-0-0-28 --iterations 10 --interval 5 --aws
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_kube_scheduler --target ip-10-0-0-28 --iterations 1 --interval 5 --aws
# 	@echo ""
# 	cd kuber_bomber && python3 reliability_tester.py --component control_plane --failure-method kill_etcd --target ip-10-0-0-28 --iterations 10 --interval 5 --aws --timeout extended
# 	@echo ""
# 	@echo "✅ Suite completa de testes AWS finalizada!"
# 	@echo "📁 Resultados salvos em: testes/2025/11/04/component/"

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
	ssh -i ~/.ssh/vockey.pem ubuntu@3.80.142.221

ssh_cli_wn:
	ssh -i ~/.ssh/vockey.pem ubuntu@13.220.170.35