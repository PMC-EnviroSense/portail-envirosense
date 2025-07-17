Pour activer l'environnement dans ton terminal:
.\.venv\Scripts\activate

exemple: C:\Users\GitHub\portail-envirosense\src\monprojet> .\.venv\Scripts\activate

Pour voir si tes changement ont été faits:
python manage.py migrate 

exemple: PS C:\Users\GitHub\portail-envirosense\src\monprojet> python manage.py migrate 

Pour runner localement:
python manage.py runserver

exemple:  PS C:\Users\keita\OneDrive\Documents\GitHub\portail-envirosense\src\monprojet> python manage.py runserver

ensuite tu vas cliquer sur le lien qui va etre générer dans le message pour voir tes modification dans le website:
 http://127.0.0.1:8000/

 PostgreSQL:
 https://www.enterprisedb.com/downloads/postgres-postgresql-downloads

 lier postgreSQL avec le projet :
 CHOISISSEZ postgreSQL 15 ET MODIFIEZ CES PARAMETRES :
                                                    Host name:localhost
                                                    PORT 5444
 une fois postgreSQL est installer creer un nouveau user en bas a guache "Login/Group Roles"
 avec les specifications suivantes:Name->envirosense_user
                                  PASSWORD->envirosense_pass
ajoutez database avec les proprietes suivantes :
                                                Database :envirosense_db
                                                OWNER:envirosense_user

sur visual studio:
 docker-compose build
 docker-compose up -d
 docker compose exec web bash
 python manage.py makemigrations
 python manage.py migrate



