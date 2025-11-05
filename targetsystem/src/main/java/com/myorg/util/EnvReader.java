package com.myorg.util;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

public class EnvReader {

    /**
     * Lê o arquivo .env localizado na raiz do projeto e retorna um Map com as variáveis de ambiente.
     *
     * @return Map contendo as chaves e valores do arquivo .env
     * @throws IOException se o arquivo não for encontrado ou ocorrer erro de leitura
     */
    public static Map<String, String> loadEnv() throws IOException {
        Map<String, String> envMap = new HashMap<>();

        File envFile = new File(".env"); // raiz do projeto
        if (!envFile.exists()) {
            throw new IOException(".env file not found in project root: " + envFile.getAbsolutePath());
        }

        try (BufferedReader reader = new BufferedReader(new FileReader(envFile))) {
            String line;
            while ((line = reader.readLine()) != null) {
                line = line.trim();

                // Ignorar linhas vazias ou comentários
                if (line.isEmpty() || line.startsWith("#")) {
                    continue;
                }

                // Dividir KEY=VALUE
                int delimiterIndex = line.indexOf('=');
                if (delimiterIndex != -1) {
                    String key = line.substring(0, delimiterIndex).trim();
                    String value = line.substring(delimiterIndex + 1).trim();

                    // Remover aspas, se houver
                    value = value.replaceAll("^\"|\"$", "");

                    envMap.put(key, value);
                    // Opcional: definir no ambiente do processo
                    System.setProperty(key, value);
                }
            }
        }

        return envMap;
    }
}
