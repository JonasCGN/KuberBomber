// --- segurança: limpa qualquer intervalo antigo salvo nesta variável ---
if (window.launchClabsInterval) {
  clearInterval(window.launchClabsInterval);
  delete window.launchClabsInterval;
}

// --- Função que tenta clicar (usa .click() e fallback com MouseEvent) ---
function tentarClicar() {
  const botao = document.getElementById('launchclabsbtn');
  if (!botao) {
    console.warn('⚠️ Botão ainda não encontrado, aguardando...');
    return;
  }

  // tentativa simples
  botao.click();

  // fallback: caso o .click() não acione o listener
  const rect = botao.getBoundingClientRect();
  const evt = new MouseEvent('click', {
    bubbles: true,
    cancelable: true,
    view: window,
    clientX: rect.left + rect.width / 2,
    clientY: rect.top + rect.height / 2,
    button: 0
  });
  botao.dispatchEvent(evt);

  console.log('✅ Clique automático em', new Date().toLocaleTimeString());
}

// --- Iniciar com intervalo em milissegundos (ex: 5000 = 5s) ---
function startAutoClick(ms = 5000) {
  // limpa intervalos antigos
  if (window.launchClabsInterval) clearInterval(window.launchClabsInterval);

  // função que inicia o auto-clicker assim que o botão existir
  function iniciarQuandoPronto() {
    const botao = document.getElementById('launchclabsbtn');
    if (botao) {
      console.log('🎯 Botão encontrado! Iniciando auto-clicker...');
      window.launchClabsInterval = setInterval(tentarClicar, ms);
      observer.disconnect(); // para de observar o DOM
    }
  }

  // verifica imediatamente
  iniciarQuandoPronto();

  // e observa o DOM se o botão ainda não estiver presente
  const observer = new MutationObserver(iniciarQuandoPronto);
  observer.observe(document.body, { childList: true, subtree: true });

  console.log('⏳ Aguardando o botão "launchclabsbtn" aparecer...');
}

// --- Para o auto-clicker ---
function stopAutoClick() {
  if (window.launchClabsInterval) {
    clearInterval(window.launchClabsInterval);
    delete window.launchClabsInterval;
    console.log('🛑 Auto-clicker parado.');
  } else {
    console.log('Nenhum auto-clicker ativo.');
  }
}

// --- CONFIGURAÇÃO DO INTERVALO ---
const segundos = 10800; // A cada 3h
const intervalo = segundos * 1000; // 5000 ms = 5 segundos

// --- INICIAR AUTOMATICAMENTE ---
startAutoClick(intervalo);