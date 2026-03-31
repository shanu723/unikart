from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import *

class DashboardTest(TestCase):

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('user_dashboard'))
        self.assertEqual(response.status_code,302)
        
    def test_dashboard_logged_in_user(self):
        user = User.objects.create_user(username='testuser',password='12345')
        self.client.login(username='testuser',password='12345')
        response = self.client.get(reverse('user_dashboard'))
        self.assertEqual(response.status_code,200)    
