#!/bin/bash

# Script simples para testar apenas as URLs sem depender de kubectl
echo "🚀 TESTE SIMPLES DOS ENDPOINTS"
echo ""

test_simple() {
    local url=$1
    local name=$2
    
    echo -n "Testing $name: "
    
    response=$(curl -s "$url")
    
    if [ $? -eq 0 ] && echo "$response" | grep -q "app"; then
        app=$(echo "$response" | jq -r '.app' 2>/dev/null || echo "parsed OK")
        echo "✅ OK - $app"
    else
        echo "❌ FAIL"
    fi
}

echo "🔸 LoadBalancer (MetalLB):"
test_simple "http://172.18.255.201/foo" "foo"
test_simple "http://172.18.255.202:81/bar" "bar"  
test_simple "http://172.18.255.203:82/test" "test"

echo ""
echo "🔸 Ingress (NGINX):"
test_simple "http://172.18.255.200/foo" "foo"
test_simple "http://172.18.255.200/bar" "bar"
test_simple "http://172.18.255.200/test" "test"

echo ""
echo "✅ URLs corretas para testes manuais:"
echo "LoadBalancer: http://172.18.255.201/foo, http://172.18.255.202:81/bar, http://172.18.255.203:82/test"
echo "Ingress: http://172.18.255.200/{foo,bar,test}"