![Taubenschlag](https://s3.gifyu.com/images/Taubenschlag.jpg)
# Taubenschlag

## What is it
A Twitter bot that handles oAuth to get authorized by multiple Twitter accounts to retweet on their behalf.

### Features:
- Top 10 Leaderboard (most retweets)
- Backup via ssh (scp to a remote server on every new user account)
- Send commands via Direct Message to the bot
    - get-bot-info
    - get-cmd-list
    - get-info
    - help
    - set-rt-level
- Supports 3 different subscription levels (1 = high class posts, 2 = informative, 3 = almost everything)

## Installation guide for debian 10
Request a Twitter dev account: https://developer.twitter.com/en/account/environments

Create an A record with domain and IP to the server of the Bot.

You need a server with Python3, a webserver and a reverse proxy. The Webserver and reverse proxy can easily get provided 
with apache2:
```
apt-get install apache2 python-certbot-apache
```
Set the hostname in `/etc/apache2/sites-enabled/000-default.conf` to `taubenschlag.yourdomain.com`
```
 systemctl restart apache2
```
Follow the certbot wizard and select `taubenschlag.yourdomain.com` for HTTPS activation and choose "redirect http to 
https"
```
certbot --apache
systemctl restart apache2
```
Now try to access the new host: https://taubenschlag.yourdomain.com

We have to configure a reverse proxy in apache:
```
sudo a2enmod proxy proxy_http
```
And add those 2 lines to `/etc/apache2/sites-enabled/000-default-le-ssl.conf`
```
ProxyPass /oAuthTwitter http://127.0.0.1:17613/oAuthTwitter
ProxyPassReverse /oAuthTwitter http://127.0.0.1:17613/oAuthTwitter
```
Restart the server:
```
shutdown -r 0
```
Download/Copy [Taubenschlag](https://github.com/bithon/Taubenschlag/releases/latest) and make the app available in 
`/opt/taubenschlag`.

Install requirements:
```
apt install python3-pip
python3 -m pip install -r /opt/taubenschlag/requirements.txt
cd /var/www/html 
rm *
ln -s /opt/taubenschlag/html/* .
```
Create two apps in https://developer.twitter.com/en/account/environments
1. Is the main app with read+write permissions (user auth to this app)
2. Is the DM sending interface app with read+write+dm permissions (user dont know about his app)

You have to provide a callback URL for app 1: `https://taubenschlag.yourdomain.com/oAuthTwitter/verify`

Copy the access tokens from the two twitter apps to `./conf.d/secrets.cfg` (use the template in 
`./conf.d/secrets.cfg_template`).

Modify `./conf.d/main.cfg` if needed.

Modify `./conf.d/rt-level-rule-set.cfg` to setup RT sources.

### Autostart and access to the Bot output
Install `screen` if it is not:
`apt install screen`

Create a cronjob as root with:
`crontab -e`

and insert the line:
```
@reboot su - root -c "screen -dm -S taubenschlag /opt/taubenschlag/taubenschlag.py"
```

Thats it, now restart and see if it works:
```
shutdown -r 0
```

After the reboot test: https://taubenschlag.yourdomain.com and try one auth!

To see the output of the bot use as root:
```
screen -x taubenschlag
```

Hint: After `screen -x` press tab-tab, to leave screen press `CTRL+a` and then `d`. 

### Autorenewal of the SSL certificate
Create a cronjob with:
```
crontab -e
```

and add this lines:
```
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

0 */12 * * * root test -x /usr/bin/certbot  -a \! -d /run/systemd/system &&  perl -e 'sleep int(rand(43200))' &&  certbot -q renew
```

### Backup
Its important to backup `/opt/taubenschlag/db/taubenschlag.json`, do it with `cat taubenschlag.json > 
backup.json`.

The bot offers in `main.cfg` the setting `ssh_backup_on_new_user`. If set to `True` the bot copy the db on every new 
user auth via ssh (scp) to a remote server. Login for scp can be defined in `secrets.cfg`.

To restore a backup just stop the bot, do `cat backup_file > taubenschlag.json` and start the bot.

## Report bugs or suggest features
https://github.com/bithon/Taubenschlag/issues

## Todo
- https://github.com/bithon/Taubenschlag/projects/1

## How to contribute
To contribute follow 
[this guide](https://github.com/bithon/Taubenschlag/blob/master/CONTRIBUTING.md).
