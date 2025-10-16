.PHONY: run_port_forward

run_port_forward:
	cd Kubernetes-Clusters && nohup ./scripts/deploy.sh --port-forwards > port_forward.log 2>&1 &
	rm -f Kubernetes-Clusters/port_forward.log

run_deploy:
	cd Kubernetes-Clusters && ./scripts/deploy.sh --local --setup
	cd Kubernetes-Clusters && ./scripts/deploy.sh --local --deploy --ubuntu
# 	cd Kubernetes-Clusters && nohup ./scripts/deploy.sh --port-forwards > port_forward.log 2>&1 &
# 	rm -f Kubernetes-Clusters/port_forward.log

run_testes:
	./teste.sh