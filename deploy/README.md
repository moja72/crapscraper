# Helper privilegiado restrito

`crapscraper_zip_helper.py` e a fonte independente do helper. Ele usa somente a
biblioteca padrao, nao importa o CrapScraper e opera exclusivamente por basenames
sob `/home/plugintema.com/downloads`. A copia instalada deve ficar fora de todo
diretorio gravavel por `adminpt`.

Instalacao futura (nao executar durante o desenvolvimento local):

```sh
sudo install -o root -g root -m 0755 deploy/crapscraper_zip_helper.py /usr/local/sbin/crapscraper-zip-helper
sudo chown root:root /usr/local/sbin/crapscraper-zip-helper
sudo chmod 0755 /usr/local/sbin/crapscraper-zip-helper
test "$(stat -c '%U:%G' /usr/bin/python3)" = "root:root"
test $(( $(stat -c '%a' /usr/bin/python3) % 100 / 10 & 2 )) -eq 0
test $(( $(stat -c '%a' /usr/bin/python3) % 10 & 2 )) -eq 0
test "$(stat -c '%U:%G' /home/plugintema.com/downloads)" = "plugi2090:nobody"
test -g /home/plugintema.com/downloads
sudo chmod +t /home/plugintema.com/downloads
test -k /home/plugintema.com/downloads
sudo -u adminpt test ! -w /usr/local/sbin/crapscraper-zip-helper
sudo -u plugi2090 test ! -w /usr/local/sbin/crapscraper-zip-helper
sudo visudo -cf deploy/crapscraper-sudoers.example
sudo install -o root -g root -m 0440 deploy/crapscraper-sudoers.example /etc/sudoers.d/crapscraper-zip-helper
sudo visudo -cf /etc/sudoers.d/crapscraper-zip-helper
sudo -u adminpt sudo -n -u plugi2090 /usr/local/sbin/crapscraper-zip-helper probe-setgid
```

Antes da instalacao, confirme que o interpretador do shebang e os diretorios de
importacao da biblioteca padrao nao sao gravaveis por `adminpt`. Nao copie o
helper para dentro do projeto, home de `adminpt`, staging ou downloads. A regra
sudoers nao autoriza shell, Python arbitrario ou utilitarios de filesystem.
O helper exige sticky bit no diretorio compartilhado para impedir que `adminpt`
renomeie ou remova artefatos pertencentes a `plugi2090` durante uma transacao.
O diretorio deve continuar com owner `plugi2090`, group `nobody` e setgid. Assim,
arquivos criados por `plugi2090` herdam `gid=nobody` sem que `plugi2090` seja
membro suplementar desse grupo. O helper apenas valida essa heranca: nunca chama
`chown`/`fchown` e nunca tenta alterar grupos do sistema. `probe-setgid` cria um
unico arquivo descartavel `CrapScraperSetgidProbe...probe`, valida owner/group,
aplica mode 0674 e o remove em `finally`, inclusive quando a validacao falha.
