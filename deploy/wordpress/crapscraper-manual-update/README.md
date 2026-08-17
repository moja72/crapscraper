# CrapScraper Manual Update

Copie esta pasta para `wp-content/plugins/` e ative o plugin. Configure somente o segredo no `wp-config.php`:

```php
define('CRAPSCRAPER_MANUAL_SECRET', 'use-o-mesmo-segredo-forte-do-crapscraper');
```

No ambiente do CrapScraper, defina `SCRAPER_WORDPRESS_MANUAL_SECRET` com o mesmo valor (mínimo de 24 caracteres). O CrapScraper usa `SCRAPER_WP_BASE_URL` para consultar a fila REST do WordPress por HTTPS. Não é necessário Cloudflare Tunnel, porta pública ou `CRAPSCRAPER_MANUAL_API_URL`.

O `autoscraper.bat` habilita o coletor com `SCRAPER_WORDPRESS_MANUAL_POLLING_ENABLED=1`. Fora do BAT, essa variável precisa ser habilitada explicitamente.

Quando o Super Admin clicar no botão, o WordPress grava o pedido localmente. Assim que o CrapScraper estiver aberto no PC, ele coleta o pedido, executa o pipeline seguro e devolve o resultado ao WordPress. O fluxo respeita `SCRAPER_UPDATE_EXECUTION_ENABLED` e `SCRAPER_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS`.

Versão 2.3.0: o painel fixo pode ser arrastado pela barra superior ou movido com as setas do teclado, além de poder ser minimizado. Posição e estado ficam salvos apenas no navegador do Super Admin; `Home` restaura a posição original. O controle continua usando o mesmo fluxo seguro e as rotas `/wp-json/crapscraper/v1/manual-updates/*` permanecem com `no-store` e integração no-cache do LiteSpeed.
