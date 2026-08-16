# CrapScraper Manual Update

Copie esta pasta para `wp-content/plugins/` e ative o plugin. Configure no `wp-config.php`:

```php
define('CRAPSCRAPER_MANUAL_API_URL', 'https://host-do-crapscraper.example');
define('CRAPSCRAPER_MANUAL_SECRET', 'use-o-mesmo-segredo-forte-do-crapscraper');
```

No ambiente do CrapScraper, defina `SCRAPER_WORDPRESS_MANUAL_SECRET` com o mesmo valor (mínimo de 24 caracteres). A URL precisa ser alcançável pelo servidor WordPress. O endpoint também respeita `SCRAPER_UPDATE_EXECUTION_ENABLED` e `SCRAPER_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS`.
