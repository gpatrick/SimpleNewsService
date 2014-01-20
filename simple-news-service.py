# Author: Greg Patrick
# Description:
# The following is a simple Python/Flask + MongoDB project that accesses Feedzilla's free REST service,
# catalogs and assigns identifiers to articles, and exposes a REST api for consumption by an iOS application.

# The application uses MongoEngine as an ODM. The application generates an authorization token that expires every
# hour.

# It was originally hosted on Heroku

from flask import Flask
from flask import request
from flask import Response
import json
from datetime import datetime, timedelta
from mongoengine import *
from base64 import b64encode
import random
import urllib2
import unicodedata

class User(Document):
    displayName = StringField()
    emailAddress = EmailField()
    userPass = StringField()
    favorites = ListField(StringField())
    
class Category(Document):
    categoryID = IntField()
    nextUpdateTime = DateTimeField()

class Article(Document):
    articleID = StringField()
    categoryID = StringField()
    author = StringField(default="Unknown")
    title = StringField(default="N/A")
    description = StringField(default="N/A")
    summary = StringField(default="N/A")
    comments = ListField(StringField())

class Comment(Document):
    commentID = StringField()
    authorID = StringField()
    articleID = StringField()
    comment = StringField()
    timeStamp = DateTimeField(default = datetime.now)    

class Token(Document):
    username = EmailField()
    token = StringField()
    expires = DateTimeField()

app = Flask(__name__)

@app.route('/')
def service_lives():
    return "Service is alive and well"

@app.route("/register", methods=["PUT"])
def register():
    connect("sns", host = "")
    #if request.method == "PUT":
    userJSON = json.loads(request.data)
    user = userJSON["username"]
    print type(user)
    userFromDatastore = User.objects(emailAddress=userJSON["username"]).first()
    print userFromDatastore
    if(userFromDatastore != None):
        return Response(status = 403)
        
    #If we get here, there is no such user
    password = b64encode(userJSON["username"] + ":" + userJSON["password"])
    user = User(displayName=userJSON["displayName"], userPass=password, emailAddress=userJSON["username"])
    user.save()
    return Response()
    
@app.route("/login", methods=["PUT"])
def login():
    connect("sns", host = "")
    print request.data
    
    credentials = unicode(request.data).strip()
    for aUser in User.objects:
        if(aUser.userPass == credentials):
            print aUser.userPass
                
    user = User.objects(userPass=credentials).first()
    
    if(user != None):
        currentToken = Token.objects(username=user.emailAddress).first()

        #Check to see if there is a valid token
        if(currentToken != None):
            return Response(currentToken.token, status=200)
        else:
            tokenString = str(random.getrandbits(128))
            expireToken = datetime.now() + timedelta(0, 60*60)
            currentToken = Token(username=user.emailAddress, token = tokenString, expires = expireToken)
            currentToken.save()
            return Response(currentToken.token, status=200)
    else:
        print "User not authenticated"
        return Response(status=401)

def authenticateUser(userToken):
    connect("sns", host = "")
    token = request.headers.get("Token")
    if(userToken == None):
        return 412

    currentUserToken = Token.objects(token=unicode(userToken)).first()
    if(currentUserToken == None):
        return 401
    elif(datetime.now() >= currentUserToken.expires):
        currentUserToken.delete()
        return 401
    else:
        return 200
    
@app.route("/users", methods=["GET"])
def users():
    connect("sns", host = "")
    token = request.headers.get("Token")
    authStatus = authenticateUser(token)
    if(authStatus == 412):
        return Response("Must supply an authentication token", status=authStatus)
    elif(authStatus == 401):
        return Response("Authorization required", status = authStatus)
    elif(authStatus == 200):
        users = User.objects
        result = []
        for user in users:
            result.append({key:user[key] for key in ("displayName", "emailAddress")})
        result = {"users":result}
        jsonString = json.dumps(result)
        return Response(jsonString, status=authStatus, mimetype="application/json")
    else:
        return Response(status=500)

@app.route("/users/<userID>", methods=["GET"])
def user(userID):
    connect("sns", host = "")
    token = request.headers.get("Token")
    authStatus = authenticateUser(token)
    if(authStatus == 412):
        return Response("Must supply an authentication token", status=authStatus)
    elif(authStatus == 401):
        return Response("Authorization required", status = authStatus)
    elif(authStatus == 200):
        user = User.objects(emailAddress=unicode(userID)).only("displayName", "emailAddress", "favorites").first()
        if(user != None):
            result = {"emailAddress":user.emailAddress, "displayName":user.displayName, "favorites":user.favorites}
            print type(result)
            print result
            #result.append({key:user[key] for key in ("displayName", "emailAddress")})
            jsonString = json.dumps(result)
            return Response(jsonString, status=authStatus, mimetype="application/json")
        else:
            return Response(status=500)

@app.route("/users/<userID>/favorites/<theArticleID>", methods=["POST"])
def favorite(userID, theArticleID):
    connect("sns", host = "")
    token = request.headers.get("Token")
    authStatus = authenticateUser(token)
    if(authStatus == 412):
        return Response("Must supply an authentication token", status=authStatus)
    elif(authStatus == 401):
        return Response("Authorization required", status = authStatus)
    elif(authStatus == 200):
        user = User.objects(emailAddress=unicode(userID)).first()
        article = Article.objects(articleID=unicode(theArticleID)).first()
        if(user != None and article != None):
            print "Current favorites:", user.favorites
            print "Appending", theArticleID, "to", userID, "'s favorites"
            if(not theArticleID in user.favorites):
                user.favorites.append(theArticleID)
                user.save()
            print "Favorite saved"
            return Response("Saved Favorite", status=authStatus, mimetype="application/json")
        else:
            return Response(status=500)

@app.route("/users/<userID>/comments/<theArticleID>", methods=["GET", "POST"])
def comment(userID, theArticleID):
    connect("sns", host = "")
    token = request.headers.get("Token")
    authStatus = authenticateUser(token)
    if(authStatus == 412):
        return Response("Must supply an authentication token", status=authStatus)
    elif(authStatus == 401):
        return Response("Authorization required", status = authStatus)
    elif(authStatus == 200):
        user = User.objects(emailAddress=unicode(userID)).first()
        article = Article.objects(articleID=unicode(theArticleID)).first()
        if(user != None and article != None):
            if(request.method == "POST"):
                print "Current comments:", article.comments
                print "Comment to add =", str(request.data)
                theCommentID = str(random.getrandbits(64))
                while(Comment.objects(commentID = theCommentID).first() != None):
                    theCommentID = str(random.getrandbits(64))
                comment = Comment(commentID=theCommentID, authorID=userID, articleID=theArticleID, comment=request.data)
                comment.save()
                article.comments.append(theCommentID)
                article.save()
                print "Comment saved"
                return Response("Saved Comment", status=authStatus, mimetype="application/json")
            elif(request.method == "GET"):
                result = []
                comments = Comment.objects(articleID=theArticleID)
                for comment in comments:
                    result.append({key:comment[key] for key in ("authorID", "comment")})
                result = {"comments":result}
                jsonString = json.dumps(result)
                return Response(jsonString, status=authStatus)
        else:
            return Response(status=500)


@app.route("/articles/categories", methods=["GET"])
def categories():
    connect("sns", host = "")
    token = request.headers.get("Token")
    authStatus = authenticateUser(token)
    if(authStatus == 412):
        return Response("Must supply an authentication token", status=authStatus)
    elif(authStatus == 401):
        return Response("Authorization required", status = authStatus)
    elif(authStatus == 200):
        response = urllib2.urlopen("http://api.feedzilla.com/v1/categories.json")
        categories = response.read()
        print categories
        
        categoriesDictionary = json.loads(categories)
        print categoriesDictionary
        result = []
        for category in categoriesDictionary:
            result.append({key:category[key] for key in ("category_id", "english_category_name")})
        result = {"categories":result}
        jsonString = json.dumps(result)
        
        return Response(jsonString, status=authStatus, mimetype="application/json")
    else:
        return Response(status=500)
    
@app.route("/articles/categories/<theCategoryID>", methods=["GET"])
def articles(theCategoryID):
    connect("sns", host = "")
    token = request.headers.get("Token")
    authStatus = authenticateUser(token)
    if(authStatus == 412):
        return Response("Must supply an authentication token", status=authStatus)
    elif(authStatus == 401):
        return Response("Authorization required", status = authStatus)
    elif(authStatus == 200):
        print "Getting Category Metadata"
        categoryMetaData = Category.objects(categoryID=unicode(theCategoryID)).first()
        print "Getting Articles..."
        categoryArticles = Article.objects(categoryID = unicode(theCategoryID))
        print categoryMetaData
        if(categoryMetaData == None or
           (categoryMetaData != None and datetime.now() >= categoryMetaData.nextUpdateTime)):
            #print "No cached articles... retrieving..."
            response = urllib2.urlopen("http://api.feedzilla.com/v1/categories/" + theCategoryID + "/articles.json")
            articles = response.read()
            #print "Retrieved Articles: ", articles
            articlesDictionary = json.loads(articles)
            articleList = articlesDictionary["articles"]
            result = []
            for article in articleList:
                #Reload the datastore before returning results
                theArticleID = str(random.getrandbits(64))
                articleTitle = article.get("title","N/A")
             #   print articleTitle
                articleAuthor = article.get("author","Unknown")
              #  print articleAuthor
                articleDescription =  article.get("description","N/A")
               # print articleDescription
                articleSummary = unicodedata.normalize("NFKD",article.get("summary","NA")).encode("ascii","ignore")
                #print articleSummary
                if(Article.objects(title=articleTitle).first() == None):
                    a = Article(articleID=theArticleID, categoryID=theCategoryID, author=articleAuthor, description=articleDescription, title=articleTitle, summary=articleSummary)
                    a.save()
              #  print "Saved article: ", articleTitle
                #result.append({"articleID":articleID, "title":articleTitle, "author":articleAuthor, "description":articleDescription, "summary":articleSummary})
                result.append({"articleID":theArticleID, "title":articleTitle, "author":articleAuthor})
                #result.append({"articleID":articleID, "title":articleTitle, "author":articleAuthor, "description":articleDescription})
            result = {"articles":result}
            jsonString = json.dumps(result)
            
            #Update category metadata (had to do this after articles have been input, or they never would be.
            if(categoryMetaData == None):
                categoryMetaData = Category(categoryID=theCategoryID)
            categoryMetaData.nextUpdateTime = datetime.now() + timedelta(0, 60*60)
            categoryMetaData.save()
            #print "Updated category metadata for id: ", theCategoryID
            
            return Response(jsonString, status=authStatus, mimetype="application/json")
        else:
            #print "Fetching cached articles"
            result = []
            if(categoryArticles != None):
                for article in categoryArticles:
                    result.append({"articleID":article.articleID, "title":article.title, "author":article.author})
            result = {"articles":result}
            jsonString = json.dumps(result)
            return Response(jsonString, status=200)
    else:
        return Response(status=500)
    
@app.route("/articles/<theArticleID>", methods=["GET"])
def article(theArticleID):
    connect("sns", host = "")
    token = request.headers.get("Token")
    authStatus = authenticateUser(token)
    if(authStatus == 412):
        return Response("Must supply an authentication token", status=authStatus)
    elif(authStatus == 401):
        return Response("Authorization required", status = authStatus)
    elif(authStatus == 200):
        article = Article.objects(articleID=unicode(theArticleID)).first()
        if(article != None):
            result = {"articleID":theArticleID, "title":article.title, "author":article.author, "description":article.description, "summary":article.summary, "comments":article.comments}
            #result = {"":user.emailAddress, "displayName":user.displayName, "favorites":[], "comments":[]}
            jsonString = json.dumps(result)
            return Response(jsonString, status=authStatus, mimetype="application/json")
        else:
            return Response(status=500)
    
    
if __name__ == '__main__':
    app.run()