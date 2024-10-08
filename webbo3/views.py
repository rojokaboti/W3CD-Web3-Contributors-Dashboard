from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.db import models
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.core.serializers.json import DjangoJSONEncoder
from .models import Treasury_guild
import json
from django.contrib.auth import authenticate, login as auth_login , logout
from django.contrib import messages
from supabase import create_client, Client
from django.conf import settings
import random
import string
from django.contrib.auth import login
from django.http import JsonResponse
import supabase
from .forms import CustomUserCreationForm

def signup(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            raw_password = form.cleaned_data.get('password1')
            user = authenticate(username=user.username, password=raw_password)
            if user is not None:
                login(request, user) 
                messages.success(request, 'Your account has been created successfully. You are now logged in.')
                return redirect('members')
            else:
                messages.error(request, 'User authentication failed.')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
            return redirect('signup')
    else:
        form = CustomUserCreationForm()
    return render(request, 'register.html', {'form': form})


def register(request):
    return render(request, 'register.html')

def signout(request):
    logout(request)
    return redirect('signin')

def signin(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Authenticate the user
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            return redirect('members') 
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'login.html')

def login_with_discord(request):
    state = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    request.session['oauth_state'] = state 

    discord_auth_url = (
        "https://discord.com/oauth2/authorize?"
        "client_id=1277781129784721471&"
        "response_type=code&"
        "redirect_uri=http%3A%2F%2F127.0.0.1%3A8000%2Fmembers&"
        "scope=identify&"
        "state={state}"
    )
    return redirect(discord_auth_url)


def discord_callback(request):
    code = request.GET.get("code")

    if not code:
        return JsonResponse({"error": "No code provided by Discord"}, status=400)

    # Initialize Supabase client
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

 
    response = supabase.auth.sign_in_with_provider(provider="discord", code=code)

    if response.status_code == 200:
        return redirect('members')
    else:
        # Handle authentication failure
        return JsonResponse({"error": "Failed to authenticate with Discord"}, status=response.status_code)

    
def first(request):
    total_minutes = Treasury_guild.objects.aggregate(total_mins=Sum('mins'))['total_mins'] or 0
    total_usd = Treasury_guild.objects.aggregate(total_usd=Sum('usd'))['total_usd'] or 0
    total_agix = Treasury_guild.objects.aggregate(total_agix=Sum('agix'))['total_agix'] or 0

    # Calculate the combined total USD + AGIX
    total_combined = total_usd + total_agix

    # Fetch the subgroup data and calculate the combined totals for each subgroup
    subgroup_data = Treasury_guild.objects.values('subgroup').annotate(
        total_mins=Sum('mins'),
        total_usd=Sum('usd'),
        total_agix=Sum('agix'),
        combined_total=Sum('usd') + Sum('agix'),
        contributor_count=Count('wallet_address', distinct=True)
    ).order_by('-total_mins')  # Order by total_mins in descending order

    # Calculate percentages for each subgroup
    for subgroup in subgroup_data:
        subgroup['combined_percentage'] = (subgroup['combined_total'] / total_combined * 100) if total_combined > 0 else 0
        subgroup['mins_percentage'] = (subgroup['total_mins'] / total_minutes * 100) if total_minutes > 0 else 0
        subgroup['usd_percentage'] = (subgroup['total_usd'] / total_usd * 100) if total_usd > 0 else 0
        subgroup['agix_percentage'] = (subgroup['total_agix'] / total_agix * 100) if total_agix > 0 else 0

    # Find the top subgroup with the most combined total
    top_subgroup_combined = max(subgroup_data, key=lambda x: x['combined_total'], default={})
    if top_subgroup_combined:
        top_subgroup_combined['combined_percentage'] = (top_subgroup_combined['combined_total'] / total_combined * 100) if total_combined > 0 else 0

    # Fetch the subgroup with the most minutes
    subgroup_with_most_minutes = Treasury_guild.objects.values('subgroup').annotate(
        total_mins=Sum('mins')
    ).order_by('-total_mins').first()
    if subgroup_with_most_minutes:
        subgroup_with_most_minutes['percentage'] = (subgroup_with_most_minutes['total_mins'] / total_minutes * 100) if total_minutes > 0 else 0

    # Fetch the subgroup with the most distinct wallet addresses
    subgroup_with_most_contributors = Treasury_guild.objects.values('subgroup').annotate(
        contributor_count=Count('wallet_address', distinct=True)
    ).order_by('-contributor_count').first()

    # Calculate percentage for the most contributors subgroup
    total_contributors = Treasury_guild.objects.values('subgroup').annotate(
        contributor_count=Count('wallet_address', distinct=True)
    ).aggregate(total_contributors=Sum('contributor_count'))['total_contributors'] or 0

    if subgroup_with_most_contributors:
        subgroup_with_most_contributors['percentage'] = (subgroup_with_most_contributors['contributor_count'] / total_contributors * 100) if total_contributors > 0 else 0

    # Calculate the total USD and AGIX
    total_usd_agix = {'total_usd': total_usd, 'total_agix': total_agix}

    context = {
        'subgroup_with_most_minutes': subgroup_with_most_minutes,
        'total_usd_agix': total_usd_agix,
        'subgroup_with_most_contributors': subgroup_with_most_contributors,
        'top_subgroup_combined': top_subgroup_combined,
        'subgroup_data': subgroup_data,
    }

    return render(request, 'first.html', context)



def workgroup(request):
    all_subgroups = list(Treasury_guild.objects.values_list('subgroup', flat=True).distinct())

    # Get selected subgroups or default to all subgroups if none selected
    selected_subgroups = request.GET.getlist('subgroups[]')
    if 'all' in selected_subgroups or not selected_subgroups:
        selected_subgroups = all_subgroups

    # Filter data based on the selected subgroups
    queryset = Treasury_guild.objects.filter(subgroup__in=selected_subgroups)

    # Fetch the default date range
    if Treasury_guild.objects.exists():
        start_date = Treasury_guild.objects.earliest('completed_at').completed_at.date()
        end_date = Treasury_guild.objects.latest('completed_at').completed_at.date()
    else:
        start_date = end_date = timezone.now().date()

    # Get selected date range from the request
    selected_start_date = request.GET.get('startdate')
    selected_end_date = request.GET.get('enddate')

    # Use the default date range if none is provided
    if not selected_start_date:
        selected_start_date = start_date
    if not selected_end_date:
        selected_end_date = end_date

    # Parse the dates if they are provided as strings
    if isinstance(selected_start_date, str):
        selected_start_date = parse_date(selected_start_date)
    if isinstance(selected_end_date, str):
        selected_end_date = parse_date(selected_end_date)

    # Apply date filtering
    queryset = queryset.filter(completed_at__date__range=[selected_start_date, selected_end_date])

    # Debugging: Print the count of records
    print(f"Selected subgroups: {selected_subgroups}")
    print(f"Selected date range: {selected_start_date} to {selected_end_date}")
    print(f"Queryset count: {queryset.count()}")

    # Annotate data for charts
    monthly_distribution = queryset.values('subgroup').annotate(
        total_mins=Sum('mins'),
        total_agix=Sum('agix'),
         total_usd=Sum('usd')
    ).order_by('subgroup')

    task_contributor_data = queryset.annotate(
    month=TruncMonth('completed_at')
).values('month').annotate(
    task_count=Count('task_name', distinct=True),
    contributor_count=Count('wallet_owner')
).order_by('month')
    monthly_agix_mins_distribution = queryset.annotate(
        month=TruncMonth('completed_at')
    ).values('month').annotate(
        total_mins=Sum('mins'),
        total_agix=Sum('agix'),
         total_usd=Sum('usd')
    ).order_by('month')

    wallet_distribution = queryset.values('wallet_address').annotate(
        total_mins=Sum('mins'),
        total_agix=Sum('agix'),
         total_usd=Sum('usd')
    ).order_by('wallet_address')

    # Get distinct subgroups for filter
    subgroups = Treasury_guild.objects.values_list('subgroup', flat=True).distinct()

    # Pass the context to the template
    context = {
        'monthly_distribution': json.dumps(list(monthly_distribution), cls=DjangoJSONEncoder),
        'task_contributor_data': json.dumps(list(task_contributor_data), cls=DjangoJSONEncoder),
        'monthly_agix_mins_distribution': json.dumps(list(monthly_agix_mins_distribution), cls=DjangoJSONEncoder),
        'wallet_distribution': json.dumps(list(wallet_distribution), cls=DjangoJSONEncoder),
        'start_date': selected_start_date,
        'end_date': selected_end_date,
        'subgroups': subgroups, 
        'selected_subgroups': selected_subgroups, 
    }

    return render(request, 'work_guild.html', context)



def workgroup_data(request):
    # Get selected date range from the request
    start_date = request.GET.get('startdate')
    end_date = request.GET.get('enddate')

    # Parse the dates if they are provided as strings
    if isinstance(start_date, str):
        start_date = parse_date(start_date)
    if isinstance(end_date, str):
        end_date = parse_date(end_date)

    # Initialize the queryset with date filter
    queryset = Treasury_guild.objects.filter(completed_at__date__range=[start_date, end_date])

    # Filter by selected subgroups
    selected_subgroups = request.GET.getlist('subgroups[]')
    if not selected_subgroups or 'all' in selected_subgroups:
        # If no subgroups are selected or "All" is selected, include all subgroups
        queryset = Treasury_guild.objects.all()
    else:
        queryset = queryset.filter(subgroup__in=selected_subgroups)

    # Annotate data for charts
    monthly_distribution = queryset.values('subgroup').annotate(
        total_mins=Sum('mins'),
        total_agix=Sum('agix'),
         total_usd=Sum('usd')
    ).order_by('subgroup')

    # Prepare chart data
    subgroup_labels = [item['subgroup'] for item in monthly_distribution]
    mins_data = [item['total_mins'] for item in monthly_distribution]
    agix_data = [item['total_agix'] for item in monthly_distribution]
    usd_data = [item['total_usd'] for item in monthly_distribution]

    return JsonResponse({
        'subgroup_chart': {
            'labels': subgroup_labels,
            'datasets': [
                {
                    'label': 'AGIX',
                    'data': agix_data,
                    'backgroundColor': 'rgba(255, 206, 86, 0.2)',  # Yellow
                    'borderColor': 'rgba(255, 206, 86, 1)',
                    'borderWidth': 1
                },
                {
                    'label': 'MINS',
                    'data': mins_data,
                    'backgroundColor': 'rgba(75, 192, 192, 0.2)',  # Teal
                    'borderColor': 'rgba(75, 192, 192, 1)',
                    'borderWidth': 1
                },
                {
                    'label': 'USD',
                    'data': usd_data,
                    'backgroundColor': 'rgba(255, 99, 132, 0.2)',  # Red
                    'borderColor': 'rgba(255, 99, 132, 1)',
                    'borderWidth': 1
                }
                ]

        }
    })



def members(request):
    contributor_name = request.GET.get('contributor_name')
    tasks = Treasury_guild.objects.filter(wallet_owner=contributor_name)

    #  the total values across all subgroups
    total_mins = tasks.aggregate(total_mins=Sum('mins'))['total_mins'] or 1
    total_agix = tasks.aggregate(total_agix=Sum('agix'))['total_agix'] or 1
    total_usd = tasks.aggregate(total_usd=Sum('usd'))['total_usd'] or 1

    # Calculate percentages for each subgroup
    subgroup_data = tasks.values('subgroup').annotate(
    mins_percentage=(Sum('mins') / total_mins) * 100,
    agix_percentage=(Sum('agix') / total_agix) * 100,
    usd_percentage=(Sum('usd') / total_usd) * 100,
    total_mins=Sum('mins')  
).distinct().order_by('-total_mins')
    top_mins_group = subgroup_data.order_by('-mins_percentage').first()
    top_agix_group = subgroup_data.order_by('-agix_percentage').first()
    top_usd_group = subgroup_data.order_by('-usd_percentage').first()

    context = {
        'contributor_name': contributor_name,
        'subgroup_data': subgroup_data,
        'top_mins_group': top_mins_group,
        'top_agix_group': top_agix_group,
        'top_usd_group': top_usd_group,
    }
    return render(request, 'Members.html', context)

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Sum

def profil(request):
    # Get the contributor_name from the GET request or use the logged-in user's username
    contributor_name = request.GET.get('contributor_name', request.user.username)
    
    tasks = Treasury_guild.objects.filter(wallet_owner=contributor_name)

    # Calculate total values across all subgroups
    total_mins = tasks.aggregate(total_mins=Sum('mins'))['total_mins'] or 1
    total_agix = tasks.aggregate(total_agix=Sum('agix'))['total_agix'] or 1
    total_usd = tasks.aggregate(total_usd=Sum('usd'))['total_usd'] or 1

    # Calculate percentages for each subgroup
    subgroup_data = tasks.values('subgroup').annotate(
        mins_percentage=(Sum('mins') / total_mins) * 100,
        agix_percentage=(Sum('agix') / total_agix) * 100,
        usd_percentage=(Sum('usd') / total_usd) * 100,
        total_mins=Sum('mins')
    ).distinct().order_by('-total_mins')
    
    top_mins_group = subgroup_data.order_by('-mins_percentage').first()
    top_agix_group = subgroup_data.order_by('-agix_percentage').first()
    top_usd_group = subgroup_data.order_by('-usd_percentage').first()

    context = {
        'contributor_name': contributor_name,
        'subgroup_data': subgroup_data,
        'top_mins_group': top_mins_group,
        'top_agix_group': top_agix_group,
        'top_usd_group': top_usd_group,
    }
    return render(request, 'profil.html', context)
