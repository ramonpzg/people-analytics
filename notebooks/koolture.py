import pandas as pd
import numpy as np
import scipy as sp
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation
import nltk, re, math, csv
# nltk.download('wordnet')
# nlkt.download('punkt')

from string import punctuation
from functools import partial
import concurrent.futures as cf
from collections import defaultdict



def comp_name_out(data, col_to_search, col_reviews, companies):
    """
    This function takes in a dataframe, the name of the column with all of 
    the companies, the name of the column with the reviews, and an iterable
    with the companies names that are in the dataset. The latter could be a list,
    set, Series, tuple, etc.
    """
    for company in companies:
        condition = (data[col_to_search] == company)
        data.loc[condition, col_reviews] = data.loc[condition, col_reviews].str.lower().str.replace(company.lower(), '', regex=False)
    
    return data



def normalize_doc(doc, stopwords=None):
    """
    This function normalizes your list of documents by taking only
    words, numbers, and spaces in between them. It then filters out
    stop words if you want to.
    """
    doc = re.sub(r'[^a-zA-Z0-9\s]', '', doc, re.I|re.A)
    doc = doc.lower()
    doc = doc.strip()
    tokens = nltk.word_tokenize(doc)
    if stopwords:
        filtered_tokens = [token for token in tokens if token not in stopwords]
    else:
        filtered_tokens = [token for token in tokens]
    doc = ' '.join(filtered_tokens)
    return doc



def root_of_word(docs, root_word_method ='stemm'):
    porter_stemmer = nltk.stem.PorterStemmer()
    snowball_stemmer = nltk.stem.SnowballStemmer('english')
    lemma = nltk.wordnet.WordNetLemmatizer()
    
    tokens = nltk.word_tokenize(docs)
    
    if root_word_method == 'lemma':
        doc = ' '.join([lemma.lemmatize(w) for w in tokens])
    elif root_word_method == 'stemm':
        doc = ' '.join([porter_stemmer.stem(w) for w in tokens])
    elif root_word_method == 'snowball':
        doc = ' '.join([snowball_stemmer.stem(w) for w in tokens])
        
    return doc


def show_topics(vectorizer, lda_model, n_words=15):
    keywords = np.array(vectorizer.get_feature_names())
    topic_keywords = []
    for topic_weights in lda_model.components_:
        top_keyword_locs = (-topic_weights).argsort()[:n_words]
        topic_keywords.append(keywords.take(top_keyword_locs))
    return topic_keywords


# def get_models(topics, tf, tup_num):
#     """
#     This functions takes in the number of topics to run the model for,
#     a tuple with the name of the company and the sparse matix and
#     a number for the element in the tuple that has the sparse matix.
#     It then returns a tuple with (company name, topic #, comph, and the model)
    
#     'Online' learning method is faster than 'batch' (offline) but has lower accuracy. Keep trade-off in mind. See link below: 
    
#     https://datascience.stackexchange.com/questions/45464/online-vs-batch-learning-in-latent-dirichlet-allocation-using-scikit-learn 
#     """
#     lda = LatentDirichletAllocation(n_components=topics, max_iter=100, learning_method='online', learning_offset=10., random_state=1234)
#     lda_model = lda.fit(tf[tup_num])
#     topicsOverWords = lda_model.components_ / lda_model.components_.sum(axis=1)[:, np.newaxis]
#     return (tf[0], topics, comph(topicsOverWords), lda_model)


def jsd(p, q, base=np.e): # JS distance between probability vectors, used to compute compH
    '''
        Implementation of pairwise `jsd` based on  
        https://en.wikipedia.org/wiki/Jensen%E2%80%93Shannon_divergence
    '''
    p = np.asarray(p)
    q = np.asarray(q)
    m = (1 / 2 * (p + q))
    return sp.stats.entropy(p, m, base) / 2 +  sp.stats.entropy(q, m, base) / 2



def conth(data): # function to measure content heterogeneity given a topic (prob) matrix
    return (1 / ((sum(map(sum, np.square(data.values)))) / data.shape[0]))


def comph(data): 
    #Transform probMatrix_df into 2D array
        
    df = pd.DataFrame()
    for x in range(len(data)): 
        jsd_list = []
        for y in range(len(data)): 
            jsd_list.append(jsd(data[x], data[y]))
        df[str(x)] = jsd_list

    #Get df lower diagonal
    mask = np.ones(df.shape, dtype='bool')
    mask[np.triu_indices(len(df))] = False
    df_lower_diagonal = df[(df>-1) & mask]
    
    distance_list = []
    for k in range(len(df)): 
    #Transform each column of df_lower_diagonal into list
        column_list = df_lower_diagonal[str(k)].values.tolist()
        #Drop nan values from column_list - to retain only actual values from lower diagonal 
        column_lower_diagonal_list = [l for l in column_list if (math.isnan(l) == False)]
        for d in column_lower_diagonal_list: 
            distance_list.append(d)
            
    return sum(distance_list) / float(len(distance_list))


def get_vectorizers(data, unique_ids, company_col, reviews_col, vrizer):
    vectorizers_dict = {}
    for comp_id in unique_ids:
        cond = (data[company_col] == comp_id) # condition to get a dataset for each company
        revs_clean = data.loc[cond, reviews_col].values # get an array of reviews for such company
        count_vect = vrizer # instantiate a vectorizer
        vect = count_vect.fit_transform(revs_clean) # fit it to the selected company reviews
        vectorizers_dict[comp_id] = (comp_id, vect, count_vect)
    
    return vectorizers_dict


# def get_vectorizers(data, unique_ids, company_col, reviews_col, vrizer):
#     vectorizers_list = []
#     for comp_id in unique_ids:
#         cond = (data[company_col] == comp_id) # condition to get a dataset for each company
#         revs_clean = data.loc[cond, reviews_col].values # get an array of reviews for such company
#         count_vect = vrizer # instantiate a vectorizer
#         vect = count_vect.fit_transform(revs_clean) # fit it to the selected company reviews
#         vectorizers_list.append((comp_id, vect, count_vect))
    
#     return vectorizers_list




def best_topics_range(model_func, vrizers_list, topics_range):
    output_dictionary = {} # dictionary for the output
    for sparse_tup in vrizers_list:

        partial_func = partial(model_func, tf=sparse_tup, tup_num=1)
        
        with cf.ProcessPoolExecutor() as e:
            output = list(e.map(partial_func, topics_range))
        
        output_dictionary[sparse_tup[0]] = output
        
    return output_dictionary

def get_models(company, topics, vrizer_dicts, unique_ids):
    """
    This functions takes in the number of topics to run the model for,
    a tuple with the name of the company and the sparse matix and
    a number for the element in the tuple that has the sparse matix.
    It then returns a tuple with (company name, topic #, comph, and the model)
    
    'Online' learning method is faster than 'batch' (offline) but has lower accuracy. Keep trade-off in mind. See link below: 
    
    https://datascience.stackexchange.com/questions/45464/online-vs-batch-learning-in-latent-dirichlet-allocation-using-scikit-learn 
    """
    output_list = []
    
    if company in unique_ids:
        
        vrizer_tups = vrizer_dicts[company]
    
        for topic in topics:
            lda = LatentDirichletAllocation(n_components=topic, max_iter=100, learning_method='online', learning_offset=10., random_state=1234)
            lda_model = lda.fit(vrizer_tups[1])
            topicsOverWords = lda_model.components_ / lda_model.components_.sum(axis=1)[:, np.newaxis]
            output_list.append((vrizer_tups[0], topic, comph(topicsOverWords), lda_model))
    
    return output_list


def build_dataframe(output_dict):
    
    if type(output_dict) == dict:
    
        dfs_list = []
        for data in output_dict.keys(): # you can use the keys to get the data
            temp_df = pd.DataFrame.from_dict(output_dict[data])
            dfs_list.append(temp_df)

        output_dfs = pd.concat(dfs_list)#.reset_index(drop=True)
        output_dfs.columns = ['company', 'topics', 'coherence', 'models']
    
    elif type(output_dict) == list:
        dfs_list = []

        for data in output_dict: # you can use the keys to get the data
            temp_df = pd.DataFrame(data)
            dfs_list.append(temp_df)

        output_dfs = pd.concat(dfs_list)#.reset_index(drop=True)
        output_dfs.columns = ['company', 'topics', 'coherence', 'models']
    
    return output_dfs



def top_two_topics(data, companies_var, coherence_var, topics_var, unique_ids, vrizers_list):
    sorted_topics = []
    comps = []
    tops = []
    for comp, tup in zip(unique_ids, vrizers_list):
        condition = data[companies_var] == comp # get each company
        the_data = data[condition] # get an exclusive dataset for a company
        top_condition = the_data[coherence_var].argsort() # get a sorted index based on coherence
        top_topics = the_data.loc[top_condition, topics_var].values # get the sorted topics based on coherence
        start, end = sorted([top_topics[-2], top_topics[-1]])
        if start == 2 and end == 10: 
            the_range = 2,5,10
        else:
            the_range = list(set(np.linspace(start, end, 10).astype(int)))
        sorted_topics.append((comp, the_range, tup[1])) # put all together
        comps.append(comp)
        tops.append(the_range)
    
    return sorted_topics, comps, tops



def get_best_topics(model_func, sorted_tuple):
    
    output_dictionary = {}

    for tup in sorted_tuple:
        partial_func = partial(model_func, tf=tup, tup_num=2)
        start, end = sorted(tup[1]) # since the top 2 topics might not be sorted, sort them first
        if start == 2 and end == 10: 
            the_range = 2, 5, 10  
            with cf.ProcessPoolExecutor() as e:
                output = list(e.map(partial_func, the_range))
            output_dictionary2[tup[0]] = output
        else:

            the_range = list(set(np.linspace(start, end, 10).astype(int))) 
            with cf.ProcessPoolExecutor() as e:
                output = list(e.map(partial_func, the_range))
            output_dictionary[tup[0]] = output
        
    return output_dictionary


def absolute_topics(data, company_col, measure_col, topics_col, model_col, vrizers_list):
    best_topics_model = defaultdict(tuple) # the output goes here

    for vrizer in vrizers_list:
        cond = data[company_col] == vrizer[0] # get each company
        filtered_data = data[cond] # to get a single dataframe
        the_topic = int(filtered_data.loc[filtered_data[measure_col].idxmax(), topics_col]) # get the best topic based on max coherence
        the_coherence = filtered_data.loc[filtered_data[measure_col].idxmax(), measure_col]
        the_model = filtered_data.loc[filtered_data[measure_col].idxmax(), model_col] # get the best model based on max coherence
        best_topics_model[vrizer[0]] = (the_topic, the_model, the_coherence)
        
    return best_topics_model



## Measures of Interest


def ent_avg(probMatrix):
    entropy_list = []
    for i in range(len(probMatrix)): 
        entropy_list.append(sp.stats.entropy(probMatrix[i]))
    return np.mean(entropy_list)


def cross_entropy(p, q):
    for i in range(len(p)):
        p[i] = p[i]+1e-12
    for i in range(len(q)):
        q[i] = q[i]+1e-12

    return -sum([p[i] * np.log2(q[i]) for i in range(len(p))])

# function to compute the average cross-entropy of a matrix
def avg_crossEnt(probMatrix): 
#    NOTE: Cross entropy is not symmetric. 
#    This function takes both cross-entropy(p,q) and cross-entropy(q,p) 
#    into account when computing the avg
    crossEntropy_list = []
    for i in range(len(probMatrix)):
        for j in range(len(probMatrix)): 
            if i != j:
                crossEntropy_list.append(cross_entropy(probMatrix[i], probMatrix[j]))
    return np.mean(crossEntropy_list)