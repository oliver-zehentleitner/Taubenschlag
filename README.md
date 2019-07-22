![Logo](https://s3.gifyu.com/images/Taubenschlag.jpg)
# Taubenschlag Twitter Bot
## Welcome to FLO Retweets! 
To participate in the campaign please join on https://retweets.floblockchain.com!
## What is it
The FLO version of https://github.com/bithon/Taubenschlag
## How to install (debian10)
Request a Twitter dev account: https://developer.twitter.com/en/account/environments

A domain routed to the server of the bot: retweets.floblockchain.com

You need a server with Python3, a webserver and a reverse proxy. The Webserver and reverse proxy can easily get provided with apache2:
```
apt-get install apache2 python-certbot-apache
```
Set the hostname in `/etc/apache2/sites-enabled/000-default.conf` to `retweets.floblockchain.com`
```
 systemctl restart apache2
```
Follow the certbot wizard and select reweets.floblockchain.com for HTTPS activation and choose "redirect http to https"
```
certbot --apache
systemctl restart apache2
```
Now try to access the new host: https://retweets.floblockchain.com

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
Download/Copy FLO Retweets Bot and make the app available in `/opt/flo-retweets`.

Install requirements:
```
apt install python3-pip
python3 -m pip install -r /opt/flo-retweets/requirements.txt
cd /var/www/html 
rm *
ln -s /opt/flo-retweets/html/* .
```
Create two apps in https://developer.twitter.com/en/account/environments
1. Is the main app with read+write permissions (user auth to this app)
2. Is the DM sending interface app with read+write+dm permissions (user dont know about his app)

You have to provide a callback URL for app 1: `https://retweets.floblockchain.com/oAuthTwitter/verify`

Copy the access tokens from the two twitter apps to `./conf.d/secrets.cfg` (use the template in 
`./conf.d/secrets.cfg_template`).

Modify `./conf.d/main.cfg` if needed.

Modify `./conf.d/rt-level-rule-set.cfg` to setup RT sources.

How to use systemd? TODO

Lets encrypt offers `certbot nenew` to make the renewal easy!

Its important to backup `/opt/flo-retweets/db/flo_retweets_bot.json`, do it with `cat flo_retweets_bot.json > 
backup.json`.

## Report bugs or suggest features
https://github.com/floblockchain/flo-retweets/issues/new/choose
## Todo
- https://github.com/floblockchain/flo-retweets/projects/1
## How to contribute
To contribute follow 
[this guide](https://github.com/floblockchain/flo-retweets/blob/master/CONTRIBUTING.md).
