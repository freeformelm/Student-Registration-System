from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from random import randint
from datetime import timedelta
from SRS.settings import EMAIL_HOST_USER, RAZOR_KEY_ID, RAZOR_KEY_SECRET
from .models import Application, Notification, Question, ApplicantResponse, Test
from .validator import validate_user_password
import razorpay

# authorize razorpay client with API Keys.
razorpay_client = razorpay.Client(auth=(RAZOR_KEY_ID, RAZOR_KEY_SECRET))
razorpay_client.set_app_details({"title" : "Django", "version" : "4.2.5"})


@staff_member_required
def populateTest(request):
    if request.method == 'POST':
        startTime = request.POST['start-time']
        endTime = request.POST['end-time']
        applications = Application.objects.all()
        for application in applications:
            application.test_start = startTime
            application.test_end = endTime
            application.save()
    return render(request, 'main/admin_startTest.html')


def send_otp(email):
    subject = 'OTP'
    otp = randint(100000, 999999)
    message = f"Your OTP is {otp}"
    from_email = EMAIL_HOST_USER
    to_list = [email]
    send_mail(subject, message, from_email, to_list)
    return otp


def Home(request):
    if request.method == 'POST':
        subject = request.POST['subject']
        message = request.POST['message']
        from_email = request.POST['email']
        to_list = [EMAIL_HOST_USER]
        send_mail(subject, message, from_email, to_list)
        return render(request, 'main/home.html')
    
    notifications = Notification.objects.filter(filter_flag='E')
    context = {'notifications': notifications}

    return render(request, 'main/home.html', context=context)


def Register(request):
    if request.method == 'POST':
        if('signup-email' in request.POST):
            email = request.POST['signup-email']
            password = request.POST['signup-password'] 
            confirm_password = request.POST['confirm-signup-password']

            if User.objects.filter(username=email).exists():
                messages.error(request, "Email already registered!!!")
                return render(request, 'main/register.html')

            if(password!=confirm_password):
                messages.error(request, 'Password do not match!!!')
                return render(request, 'main/register.html')
            
            # validators = [MinimumLengthValidator, NumberValidator, UppercaseValidator]
            try:
                validate_user_password(password)
            except ValidationError as e:
                for error in e.message_dict['password']:
                    messages.error(request, error)
                return render(request, 'main/register.html')

            otp = send_otp(email)
            request.session['otp'] = otp
            request.session['email'] = email
            request.session['password'] = password
            messages.success(request, "OTP has been sent to your email address!!")
            return render(request, 'main/otp.html')
        
        if('otp' in request.POST):
            if(int(request.POST['otp'])==int(request.session['otp'])):
                email = request.session['email']
                password = request.session['password']
                User.objects.create_user(username=email, email=email, password=password)
                user = authenticate(username=email, password=password)
                login(request, user)
                return redirect('main:FillApplication')
            else:
                messages.error(request, "Invalid OTP!!!")
                return render(request, 'main/otp.html')
        
    return render(request, 'main/register.html')


def Login(request):
    if request.method == 'POST':
        # print(request.POST)
        email = request.POST['signin-email']
        password = request.POST['signin-password']

        user = authenticate(username=email, password=password)

        if user is not None:
            login(request, user)
            next = request.GET.get('next')
            try:
                app = Application.objects.get(student=user)
            except Application.DoesNotExist:
                if next:
                    messages.error(request, "The registration period is over! You are not eligible to give test.")
                    return redirect('main:Login')
                else:                    
                    return redirect('main:FillApplication')
            
            if next:
                return redirect(next)
            else:
                if(app.payment_id==None):
                    return redirect('main:PayFees')
                else:
                    return redirect('main:Dashboard')
                
        else:
            messages.error(request, 'Incorrect Email or Password!!!')
            return render(request, 'main/login.html')

    return render(request, 'main/login.html')


def Forget(request):
    if request.method=='POST':
        if 'otp' in request.POST:
            if(int(request.POST['otp'])==int(request.session['otp'])):
                messages.success(request, "OTP matched successfully!!!")
                return render(request, 'main/change_password.html')
            else:
                messages.error(request, "Invalid OTP!!!")
                return render(request, 'main/otp.html')
            
        if 'change-password' in request.POST:
            email = request.session['email']
            password = request.POST['change-password']
            confirm_password = request.POST['confirm-change-password']

            if password!=confirm_password : 
                messages.error(request, "Password do not match!!!")
                return render(request, 'main/change_password.html')
            
            try:
                validate_user_password(password)
            except ValidationError as e:
                for error in e.message_dict['password']:
                    messages.error(request, error)
                return render(request, 'main/change_password.html')
            
            user = User.objects.get(username=email)
            user.set_password(password)
            user.save()
            messages.success(request, "Your password has been successfully changed !!!")
            return redirect('main:Login')

        if 'forget-email' in request.POST:
            email = request.POST['forget-email']
            if(User.objects.filter(username=email).exists()):
                otp = send_otp(email)
                request.session['otp'] = otp
                request.session['email'] = email
                messages.success(request, "OTP has been sent to your email address!!")
                return render(request, 'main/otp.html')
            else:
                messages.error(request, 'Email Does Not Exist')
                return render(request, 'main/forget.html')

    return render(request, 'main/forget.html')


@login_required
def FillApplication(request):
    user = request.user
    if request.method == 'POST':
        name = request.POST['fname'] + ' ' + request.POST['mname'] + ' ' + request.POST['lname']
        gender = request.POST.get('gender')
        dob = request.POST['dob']
        print(request.POST.get('gender'))
        
        address = request.POST['line-1'] + ', ' + request.POST.get('line-2') + ', ' + request.POST['city'] + ', ' + request.POST['state'] + ', ' + request.POST['country'] + ', ' + request.POST['postal-code']
        phone = request.POST['phone']
        alt_phone = request.POST['alt_phone']

        father = request.POST['father']
        mother = request.POST['mother']

        ssc = request.POST['ssc']
        ssc_per = request.POST['ssc_per']
        hsc = request.POST['hsc']
        hsc_per = request.POST['hsc_per']
        gujcet = request.POST['gujcet']
        jee = request.POST['jee']

        id_proof = request.FILES.get('id_proof')
        photo = request.FILES.get('photo')
        marks_10 = request.FILES.get('marks_10')
        marks_12 = request.FILES.get('marks_12')
        Application.objects.create(name=name, gender=gender, dob=dob, address=address, phone=phone, alt_phone=alt_phone, father=father, mother=mother, ssc=ssc, ssc_per=ssc_per, hsc=hsc, hsc_per=hsc_per, gujcet=gujcet, jee=jee, student=user, id_proof=id_proof, photo=photo, marks_10=marks_10, marks_12=marks_12)

        return redirect('main:PayFees')

    return render(request, 'main/fill_application.html')

def PayFees(request):
    user = request.user
    applicant = Application.objects.get(student=user)

    #Razorpay Payment
    currency = 'INR'
    amount = 100*100  # Rs. 100

    razorpay_order = razorpay_client.order.create(dict(amount=amount, currency=currency, payment_capture='0'))
    razorpay_order_id = razorpay_order['id']
    applicant.order_id = razorpay_order_id
    applicant.save()

    razorpay_order = razorpay_client.order.create(dict(amount=amount, currency=currency, payment_capture='1'))
    razorpay_order_id = razorpay_order['id']

    razorpay = "https://razorpay.com/payment-button/pl_MgAaDNUDkk2msX/view/?utm_source=payment_button&utm_medium=button&utm_campaign=payment_button"

    request.session['user'] = user.email
    request.session.set_expiry(0)

    return HttpResponseRedirect(razorpay)

def success(request, amount):
    if not request.session.get('user'):
        return redirect('main:Home')

    if User.objects.filter(username=request.session.get('user')).exists():
        user = User.objects.get(username=request.session['user'])
        applicant = Application.objects.get(student=user)
        applicant.payment_id = request.GET.get('payment_id', '')
        applicant.save()
        request.session.pop('user', '')
        return redirect('main:Dashboard')
    else:
        messages.error(request,'The payment failed! Please try Again.')
        return redirect('main:Home')


@login_required
def Dashboard(request):
    user = request.user
    app = Application.objects.get(student=user)
    notification = Notification.objects.filter(recipient=app) | Notification.objects.filter(filter_flag='Q') | Notification.objects.filter(filter_flag=app.app_status)
    
    context = {'application' : app, 'notifications' : notification}
    
    return render(request, 'main/dashboard.html', context=context)
    

def Logout(request):
    logout(request)
    return redirect('main:Home')


@login_required()
def startTest(request):
    #Add constraint for Application Status = Accepted!
    user = request.user
    try:
        user_application = Application.objects.get(student=user)
    except Application.DoesNotExist:
        messages.error(request, "The registration period is over! You are not eligible to give test.")
        return redirect('main:Login')
    
    timestampToday = timezone.now()
    if timestampToday < user_application.test_start:
        messages.error(request, f"The test will start from {user_application.test_start}!")
        return redirect('main:Dashboard')
    if timestampToday > user_application.test_end:
        messages.error(request, "The test window has ended!")
        return redirect('main:Dashboard')
    
    try:
        test = Test.objects.get(app_no=user_application)
        if test.test_end is not None:
            messages.success(request, "Your test has already ended! You can now view your result")
            return redirect('main:Dashboard')
    except Test.DoesNotExist:
        pass
    
    if 'start' in request.GET:
        try:
            test = Test.objects.get(app_no=user_application)
        except Test.DoesNotExist:
            test = Test.objects.create(app_no=user_application, test_start=timezone.now())
        return redirect(reverse('main:Next_Question', args=(1,)))
    

    
    return render(request,'main/instructions.html')


def nextQuestion(request, question_id):
    if request.user.is_authenticated:
        #Write a constraint where the student should have testWindowStart timestamp. ->In case he jumps directly to url /test/1. This constraint will also support the test window constraint written in view above.
        user = request.user
        question = Question.objects.get(qid = question_id)
        qCount = Question.objects.all().count()
        options = [question.op1, question.op2,question.op3,question.op4]
        user_application = Application.objects.get(student=user)
        test = Test.objects.get(app_no=user_application)
        if test.test_end is not None:
            messages.success(request, "Your test has already ended! You can now view your result")
            return redirect('main:Dashboard')

        time_left = test.test_start + timedelta(minutes=5) - timezone.now()
        hours, remainder = divmod(time_left.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
    else:
        return redirect('main:StartTest')

    try:
        user_response = ApplicantResponse.objects.get(app_no = user_application, ques = question)
    except ApplicantResponse.DoesNotExist:
        user_response = ApplicantResponse.objects.create(app_no = user_application, ques = question)

    if request.method =='POST':    
        if 'clear' in request.POST:
            user_response.response = ""
            user_response.save()
            return redirect(reverse('main:Next_Question', args=(question.qid,)))
           
        user_curr_ans = request.POST.get('answer')
        if user_response is not None:
            user_response.response = user_curr_ans
            user_response.save()
        else:
            user_response = ApplicantResponse.objects.create(app_no__user = user, ques__qid = question_id, response = user_curr_ans)

        if 'end' in request.POST:
            return redirect('main:EndTest')
        
        if 'submit' in request.POST:
            if(question_id==Question.objects.count()):
                messages.success(request,'You have reached the end of test. Please review your answers and submit')
                return redirect(reverse('main:Next_Question', args=(1,)))
            next_question = Question.objects.get(qid=question_id+1)
            #This is not required ig
            # options = [next_question.op1, next_question.op2,next_question.op3,next_question.op4]
            return redirect(reverse('main:Next_Question', args=(next_question.qid,)))
            
    context = {
                'question': question, 
                'options': options,
                'response': user_response.response, 
                'iterateover': range(1,5), 
                'count': qCount,
                'countIterable': range(1,qCount+1),
                'hours': hours,
                'minutes': minutes,
                'seconds': seconds,    
            }
    
    return render(request, 'main/questions.html', context=context)

def EndTest(request):
    if request.user.is_authenticated:
        user = request.user
        user_application = Application.objects.get(student=user)
        responses = ApplicantResponse.objects.filter(app_no=user_application)
        test = Test.objects.get(app_no=user_application)
    else:
        return redirect('main:StartTest')

    test.test_end=timezone.now()

    total = Question.objects.count()
    score = 0
    for i in responses:
        question = i.ques
        if question.ans==i.response:
            score+=1
    test.score=score
    test.save()

    context = {'score':score, 'total': total}
    return render(request, 'main/result.html', context=context)

@login_required
def Result(request):
    user = request.user
    app = Application.objects.get(student=user)
    test = Test.objects.get(app_no=app)
    total = Question.objects.count()
    score = test.score
    context = {'total':total, 'score':score}

    return render(request, 'main/result.html', context=context)