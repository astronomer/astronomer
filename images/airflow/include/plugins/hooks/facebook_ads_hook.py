import json
from airflow.hooks.base_hook import BaseHook
from facebookads.api import FacebookAdsApi
from facebookads.adobjects.user import User

class FacebookAdsHook(BaseHook):
    """
    Interact with FacebookAds
    """
    def __init__(self, facebook_ads_conn_id=None):
        self.facebook_ads_conn_id = facebook_ads_conn_id

    def get_conn(self):
        conn = self.get_connection(self.facebook_ads_conn_id)
        extra = json.loads(conn.extra)
        FacebookAdsApi.init('', '', extra.get('access_token'))
        return User(fbid='me')

    def get_ad_accounts(self):
        facebook_ads = self.get_conn()
        return facebook_ads.get_ad_accounts()
