import random
import csv
import math
import pandas
import codecs
import numpy as np
from collections import Counter
from nltk.tokenize import word_tokenize
from IPython.display import HTML, display

SMOOTH_CONST = 0.001 # we want this to be smaller than 1/n where n is the size of the largest training category. that way, any word that has appeared exactly once (with category c) in training will still have a larger probability for category c, than any other category c'
TRAIN_SPLIT = 0.8

categories = ['Energy', 'Food', 'Medical', 'None', 'Water']
need_or_resource_labels = ['need', 'resource', 'N/A']


class Tweet(object):
  def __init__(self, tweetSurfaceForm, category, need_or_resource):
    if isinstance(tweetSurfaceForm, str):
      self.tokenList = word_tokenize(tweetSurfaceForm)
    else:
      self.tokenList = word_tokenize(tweetSurfaceForm.decode('utf-8','ignore'))
    self.tokenList = [t.lower() for t in self.tokenList] # lowercase
    self.tokenSet = set(self.tokenList)
    self._bigramList = [(self.tokenList[idx], self.tokenList[idx+1]) for idx in range(len(self.tokenList)-1)]
    self._featureSet = set(self._bigramList).union(self.tokenSet)
    self.category = category
    self.need_or_resource = need_or_resource

  def __getitem__(self,index):
    return self.tokenList[index]

  def idx(self, token):
    return self.tokenList.index(token)

  def __unicode__(self):
    return " ".join(self.tokenList)

  def __str__(self):
    return str(self).encode('utf-8')

  def __repr__(self):
      return self.__str__()


def read_csv(path):
   data = {}
   with open(path) as f:
     reader = csv.reader(f)
     for row in reader:
       (tweetId, tweetText, category, need_or_resource) = row
       assert category in categories
       assert need_or_resource in need_or_resource_labels
       if need_or_resource == "N/A":
         assert category == "None"
       assert tweetId not in data.keys()
       data[tweetId] = Tweet(tweetText, category, need_or_resource)
   data = data.values() # list of Tweets
   return data


def read_data(train_path = 'data/labeled-data-singlelabels-train.csv',
              test_path = 'data/labeled-data-singlelabels-test.csv'):
  """Returns two lists of tweets: the train set and the test set"""
  train_tweets = read_csv(train_path)
  test_tweets = read_csv(test_path)
  return train_tweets, test_tweets


def show_confusion_matrix(predictions):
  """Displays a confusion matrix as a HTML table.
  Rows are true label, columns are predicted label.
  predictions is a list of (tweet, predicted_category) pairs"""
  num_categories = len(categories)
  conf_mat = np.zeros((num_categories, num_categories), dtype=np.int32)
  for (tweet,predicted_category) in predictions:
    gold_idx = categories.index(tweet.category)
    predicted_idx = categories.index(predicted_category)
    conf_mat[gold_idx, predicted_idx] += 1
  df = pandas.DataFrame(data=conf_mat, columns=categories, index=categories)
  display(HTML(df.to_html()))


def class2color_style(s):
  class2color = {
    'Energy' : 'red',
    'Food': 'orange',
    'Medical': 'green',
    'None': 'gray',
    'Water': 'blue',
    'resource': 'purple',
    'need': 'pink',
    'N/A': 'gray',
  }
  try:
    return "color: %s" % class2color[s]
  except KeyError:
    return "color: black"


def show_tweets(tweets, search_term=None):
  """Displays a HTML table of tweets alongside labels"""
  if search_term is not None:
    tweets = [t for t in tweets if search_term in str(t).lower()]
  columns = ['Text', 'Category', 'Need or resource']
  data = [[str(t), t.category, t.need_or_resource] for t in tweets]
  pandas.set_option('display.max_colwidth', -1)
  df = pandas.DataFrame(data, columns=columns)
  s = df.style.applymap(class2color_style)\
              .set_properties(**{'text-align': 'left'})
  display(HTML(s.render()))


def show_predictions(predictions, show_mistakes_only=False):
  """Displays a HTML table comparing true categories to predicted categories.
  predictions is a list of (tweet, predicted_category) pairs"""
  if show_mistakes_only:
    predictions = [(t,p) for (t,p) in predictions if t.category!=p]
  columns = ['Text', 'True category', 'Predicted category']
  data = [[str(t), t.category, predicted_category] for (t,predicted_category) in predictions]
  pandas.set_option('display.max_colwidth', -1)
  df = pandas.DataFrame(data, columns=columns)
  s = df.style.applymap(class2color_style)\
              .set_properties(**{'text-align': 'left'})
  display(HTML(s.render()))



def most_discriminative(tweets, token_probs, prior_probs):
  """Prints, for each category, which tokens are most discriminative i.e. maximize P(category|token), including normalization by P(token)"""
  all_tokens = set([token for tweet in tweets for token in tweet.tokenSet])

  token2dist = {} # maps token to a probability distribution over categories, for a tweet containing just this token

  for token in all_tokens:
    single_token_tweet = Tweet(token, "", "")
    log_dist = {c: get_log_posterior_prob(single_token_tweet, prior_probs[c], token_probs[c]) for c in categories}
    min_log_dist = min(log_dist.values())
    log_dist = {c: l+min_log_dist for c,l in log_dist.iteritems()} # shift so smallest value is 0 before taking exp
    dist = {c:math.exp(l) for c,l in log_dist.iteritems()} # take exp
    s = sum(dist.values())
    dist = {c: dist[c]/s for c in categories} # normalize
    token2dist[token] = dist

  # for each category print the tokens that maximize P(C|token) (normalized by P(token))
  print("MOST DISCRIMINATIVE TOKENS: \n")
  for c in categories:
    probs = [(token,dist[c]) for token,dist in token2dist.iteritems()]
    probs = sorted(probs, key=lambda x: x[1], reverse=True)
    print("{0:20} {1:10}".format("TOKEN", "P(%s|token)"%c))
    for (token,p) in probs[:10]:
        print("{0:20} {1:.4f}".format(token.encode('utf8'),p))
    print("")


def get_category_f1(predictions, c):
  """
  Inputs:
      predictions: a list of (tweet, predicted_category) pairs
      c: a category
  Calculate the precision, recall and F1 for a single category c (e.g. Food)
  """

  true_positives = 0.0
  false_positives = 0.0
  false_negatives = 0.0

  for (tweet, predicted_category) in predictions:
      true_category = tweet.category
      if true_category == c and predicted_category == c:
          true_positives += 1
      elif true_category == c and predicted_category != c:
          false_negatives += 1
      elif true_category != c and predicted_category == c:
          false_positives += 1

  if true_positives == 0:
      precision = 0.0
      recall = 0.0
      f1 = 0.0
  else:
      precision = true_positives*100 / (true_positives + false_positives)
      recall = true_positives*100 / (true_positives + false_negatives)
      f1 = 2*precision*recall / (precision + recall)

  print(c)
  print("Precision: ", precision)
  print("Recall: ", recall)
  print("F1: ", f1)
  print("")
#     print "Class %s: precision %.2f, recall %.2f, F1 %.2f" % (c, precision, recall, f1)

  return f1


def evaluate(predictions):
  """Calculate average F1"""
  average_f1 = 0
  for c in categories:
    f1 = get_category_f1(predictions, c)
    average_f1 += f1

  average_f1 /= len(categories)
  print("Average F1: ", average_f1)


def calc_probs(tweets, c):
    """
    Input:
        tweets: a list of tweets
        c: a string representing a category
    Returns:
        prob_c: the prior probability of category c
        feature_probs: a Counter mapping each feature to P(feature|category c)
    """
    num_tweets = len(tweets)
    num_tweets_about_c = len([t for t in tweets if t.category==c])
    prob_c = float(num_tweets_about_c)/num_tweets
    feature_counts = Counter() # maps token -> count and bigram -> count
    for tweet in tweets:
        if tweet.category==c:
          for feature in tweet._featureSet:
            feature_counts[feature] += 1
    feature_probs = Counter({feature: float(count)/num_tweets_about_c for feature,count in feature_counts.iteritems()})
    return prob_c, feature_probs


def learn_nb(tweets):
  feature_probs = {}
  prior_probs = {}
  for c in categories:
    prior_c, feature_probs_c = calc_probs(tweets, c)
    feature_probs[c] = feature_probs_c
    prior_probs[c] = prior_c
  return prior_probs, feature_probs


def get_log_posterior_prob(tweet, prob_c, feature_probs_c):
    """Calculate the posterior P(c|tweet).
    (Actually, calculate something proportional to it).

    Inputs:
        tweet: a tweet
        prob_c: the prior probability of category c
        feature_probs_c: a Counter mapping each feature to P(feature|c)
    Return:
        The posterior P(c|tweet).
    """
    log_posterior = math.log(prob_c)
    for feature in tweet._featureSet:
        if feature_probs_c[feature] == 0:
            log_posterior += math.log(SMOOTH_CONST)
        else:
            log_posterior += math.log(feature_probs_c[feature])
    return log_posterior


def classify_nb(tweet, prior_probs, token_probs):
    """Classifies a tweet. Calculates the posterior P(c|tweet) for each category c,
    and returns the category with largest posterior.
    Input:
        tweet
    Output:
        string equal to most-likely category for this tweet
    """
    log_posteriors = {c: get_log_posterior_prob(tweet, prior_probs[c], token_probs[c]) for c in categories}
    return max(log_posteriors.keys(), key=lambda c:log_posteriors[c])


def get_box_contents(n_boxes = 2):
    box1 = ["red"] * 10 + ["blue"] * 39 + ["yellow"] * 1 + ["green"] * 27 + ["orange"] * 23
    box2 = ["red"] * 53 + ["blue"] * 5 + ["yellow"] * 25 + ["green"] * 9 + ["orange"] * 8
    box3 = ["red"] * 15 + ["blue"] * 15 + ["yellow"] * 64 + ["green"] * 3 + ["orange"] * 3
    box4 = ["red"] * 5 + ["blue"] * 5 + ["yellow"] * 5 + ["green"] * 5 + ["orange"] * 80


    assert(len(box1) == 100)
    assert(len(box2) == 100)
    assert(len(box3) == 100)
    assert(len(box4) == 100)


    random.shuffle(box1)
    random.shuffle(box2)
    random.shuffle(box3)
    random.shuffle(box4)

    boxes = [box1, box2, box3, box4][0:n_boxes]

    return boxes




def visualize_tweet(tweet, prior_probs, token_probs):
    """
        Visualizes a tweet and its probabilities in an IPython notebook.
        Input:
            tweet: a tweet as a string
            prior_probs: priors for each category
            token_probs: a dictionary of Counters that contain the unigram
               probabilities for each category

    """


    # boileplate HTML part 1
    html = """
    <div id="viz-overlay" style="display:none;position:absolute;width:250px;height:110px;border: 1px solid #000; padding:8px;  background: #eee;">
	<p>
       <span style="color:orange;">P(<span class="viz-token-placeholder"></span> | food) = <span id="viz-p-food"></span></span><br>
	   <span style="color:blue;">P(<span class="viz-token-placeholder"></span> | water) = <span id="viz-p-water"></span><br>
	   <span style="color:green;">P(<span class="viz-token-placeholder"></span> | medical) = <span id="viz-p-medical"></span><br>
	   <span style="color:red;">P(<span class="viz-token-placeholder"></span> | energy) = <span id="viz-p-energy"></span><br>
	   <span style="color:gray;">P(<span class="viz-token-placeholder"></span> | none) = <span id="viz-p-none"></span></p>
    </p>
    </div>

    <div id="viz-tweet" style="padding: 190px 0 0;">
    """


    tokens = tweet.tokenList
    categories = ["None", "Food", "Medical", "Energy", "Water"]
    for token in tokens:
        probs = [token_probs['None'][token], token_probs['Food'][token],
                token_probs['Medical'][token], token_probs['Energy'][token],
                token_probs['Water'][token]]
        idx = np.argmax(probs) if sum(probs) > 0 else 0
        max_class = categories[idx]

        html += '<span style="%s" class="viz-token" data-food="%f" data-none="%f" data-medical="%f" data-energy="%f" data-water="%f">%s</span> ' \
                  % (class2color_style(max_class), token_probs['Food'][token], token_probs['None'][token], token_probs['Medical'][token],
                  token_probs['Energy'][token], token_probs['Water'][token], token)

    # Predicted category.
    predicted_category = classify_nb(tweet, prior_probs, token_probs)
    html += '<p><strong>Predicted category: </strong> <span style="%s"> %s</span><br>' \
              % (class2color_style(predicted_category), predicted_category)
    html += '<strong>True category: </strong> <span style="%s"> %s</span></p>' \
              % (class2color_style(tweet.category), tweet.category)

    #Javascript
    html += """
    </div>
     <script type="text/javascript">
	$(document).ready(function() {
		$("span.viz-token").mouseover(function() {
			$("span.viz-token").css({"font-weight": "normal"});
			$(this).css({"font-weight": "bold"});
			$("span.viz-token-placeholder").text($(this).text());
			$("#viz-p-food").text($(this).data("food"));
			$("#viz-p-water").text($(this).data("water"));
			$("#viz-p-medical").text($(this).data("medical"));
			$("#viz-p-energy").text($(this).data("energy"));
			$("#viz-p-none").text($(this).data("none"));
			$("#viz-overlay").show();
			$("#viz-overlay").offset({left:$(this).offset().left-110+$(this).width()/2, top:$(this).offset().top - 140});
		});
	});
    </script>

    """

    display(HTML(html))
