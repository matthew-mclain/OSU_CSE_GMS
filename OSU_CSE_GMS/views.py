from django.shortcuts import redirect, render
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.views.defaults import server_error
from .forms import CourseForm, SectionForm, SignUpFormAdmin, SignUpFormStudent, ApplicationForm
from .models import Course, Student, Assignment, Section, UnassignedStudent, Instructor, PreviousClassTaken, Administrator
import logging
from .algo.algo import massAssign
from django.contrib.auth import authenticate, login
from django.contrib import messages
from .services import permissions

LOGGER = logging.getLogger('django')
REJECTION_LOGGER = logging.getLogger('rejection_reason_logging')

def is_student(user):
    has_permission = permissions.has_group(user, permissions.STUDENT_GROUP)
    log_permission_result(has_permission, permissions.STUDENT_GROUP)
    return has_permission

def is_administrator(user):
    has_permission = permissions.has_group(user, permissions.ADMINISTRATOR_GROUP)
    log_permission_result(has_permission, permissions.ADMINISTRATOR_GROUP)
    return has_permission

def is_instructor(user):
    has_permission = permissions.has_group(user, permissions.INSTRUCTOR_GROUP)
    log_permission_result(has_permission, permissions.INSTRUCTOR_GROUP)
    return has_permission

def log_permission_result(has_permission, permission_name):
    if has_permission:
        LOGGER.info(f'User has {permission_name} permissions')
    else:
        LOGGER.warning(f'User does not have {permission_name} permissions')

@login_required
def administrator(request):
    context = {}
    userOfReq = request.user

    if not is_administrator(userOfReq):
        raise PermissionDenied
   
    if not Administrator.objects.filter(user=userOfReq).exists():
        return redirect("home")
    
    course_form = CourseForm()
    if request.method == 'POST':
        if 'add_course' in request.POST:
            LOGGER.info('Adding New Course')
            course_form = CourseForm(request.POST)
            if course_form.is_valid():
                course_form.save()
        elif 'update_course' in request.POST:
            course_number = request.POST['course_number']
            LOGGER.info(f'Updating Course with course number: {course_number}')
            course = Course.objects.get(course_number=course_number)
            course_form = CourseForm(request.POST, instance=course)
            if course_form.is_valid():
                course_form.save()
        elif 'delete_course' in request.POST:
            course_number = request.POST['course_number']
            LOGGER.info(f'Deleting Course with course number: {course_number}')
            course = Course.objects.get(course_number=course_number)
            course.delete()

    # Fetch all existing courses, sections, instructors from the database
    courses = Course.objects.all()
    sections = Section.objects.all()
    instructors = Instructor.objects.all()

    LOGGER.info(f'Retrieved {courses.count()} courses, {sections.count()} sections, and {instructors.count()} instructors')

    # Sort the courses by course_number
    sort_direction = 'asc'
    if 'sort' in request.GET:
        sort_direction = request.GET['sort']
        sort_direction = 'asc' if sort_direction == 'desc' else 'desc'

    if sort_direction == 'asc':
        courses = courses.order_by('course_number')
    else:
        courses = courses.order_by('-course_number')

    # Query to get all courses that have at least one section that needs at least one grader
    courses_needing_graders = Course.objects.filter(section__num_graders_needed__gt=0).distinct()

    context = {
        'course_form': course_form,
        'courses': courses,
        'sections': sections,
        'instructors': instructors,
        'courses_needing_graders': courses_needing_graders,
        'sort_direction': sort_direction,
    }
    
    return render(request, 'administrator.html', context)

@login_required
def course_detail(request, course_number):
    context = {}
    userOfReq = request.user

    if not is_administrator(userOfReq):
        raise PermissionDenied

    if not Administrator.objects.filter(user=userOfReq).exists():
       return redirect("home")
    
    section_form = SectionForm()
    if request.method == 'POST':
        if 'add_section' in request.POST:
            LOGGER.info(f'Adding Section to Course Number: {course_number}')
            section_form = SectionForm(request.POST)
            if section_form.is_valid():
                section_form.save()
        elif 'update_section' in request.POST:
            section_number = request.POST['section_number']
            LOGGER.info(f'Updating Section with section number: {section_number}')
            section = Section.objects.get(section_number=section_number, course_number=course_number)
            section_form = SectionForm(request.POST, instance=section)
            if section_form.is_valid():
                section_form.save()
        elif 'delete_section' in request.POST:
            section_number = request.POST['section_number']
            LOGGER.info(f'Deleting Section with section number: {section_number}')
            section = Section.objects.get(section_number=section_number, course_number=course_number)
            section.delete()
        elif 'add_assignment' in request.POST:
            add_assignment(request=request)
        elif 'delete_assignment' in request.POST:
            assignment_id = request.POST['assignment_id']
            LOGGER.info(f'Deleting Assignment with id: {assignment_id}')
            assignment = Assignment.objects.get(id=assignment_id)
            assignment.delete()

    course = Course.objects.get(course_number=course_number)
    sections = Section.objects.filter(course_number=course_number)
    instructors = Instructor.objects.all()
    assignments = Assignment.objects.filter(section_number__course_number=course_number)
    students = Student.objects.filter(assignment__in=assignments)
    context = {
        'section_form': section_form,
        'course': course,
        'sections': sections,
        'instructors': instructors,
        'assignments': assignments,
        'students': students
    }
    return render(request, 'course_detail.html', context)

def add_assignment(request):
    section_number = request.POST['section_id']
    student_email = request.POST['student_email']
    LOGGER.info(f'Adding Assignment to Section with section number: {section_number}')
    try:
        section = Section.objects.get(pk=section_number)
        student = Student.objects.get(email=student_email)
        assignment = Assignment(section_number=section, student_id=student, status='PENDING')
        assignment.save()
    except Student.DoesNotExist:
        messages.error(request, 'Student with email does not exist.')


@login_required
def dashboard(request):
    userOfReq = request.user
    if request.user.is_authenticated:
        if permissions.has_group(userOfReq, permissions.ADMINISTRATOR_GROUP):
            return redirect("administrator")
        elif permissions.has_group(userOfReq, permissions.STUDENT_GROUP):
            return redirect("student")
        elif permissions.has_group(userOfReq, permissions.INSTRUCTOR_GROUP):
            return redirect("instructor_dashboard")
        else:
            return redirect("home")
    else:
        return redirect("home")
    

@login_required
def create_admin(request):
    userOfReq = request.user

    if not is_administrator(userOfReq):
        raise PermissionDenied

    # if not Administrator.objects.filter(user=userOfReq).exists():
    #    return redirect("home")
    form = SignUpFormAdmin()
    if request.method == 'POST':
        form = SignUpFormAdmin(request.POST)
        if form.is_valid():
            LOGGER.info('Create admin Form Valid')
            form.save()

            first_name = form.cleaned_data.get('first_name')
            last_name = form.cleaned_data.get('last_name')
            username = form.cleaned_data.get('username')
            email = form.cleaned_data.get('email')

            user = User.objects.get(username=username)
            administrator = Administrator.objects.create(user=user, email=email, first_name = first_name, last_name = last_name)
            administrator.save()
            if administrator.pk:
                LOGGER.info(f'Created Administrator with id: {administrator.pk} associated with auth_user with id: {user.pk}')
            else:
                LOGGER.error(f'Failed to create Administrator to associate with user id: {user.pk}')

            return redirect('administrator')
        else:
            LOGGER.warning(f'Admin create Form not valid: {form.errors}')
        
    context = {
        'form' : form
    }

    return render(request, 'registration/admin_create.html', context)


def sign_up(request):
    form = SignUpFormStudent()

    if request.method == 'POST':
        form = SignUpFormStudent(request.POST)

        if form.is_valid():
            LOGGER.info('Sign Up Form Valid')
            form.save()
            first_name = form.cleaned_data.get('first_name')
            last_name = form.cleaned_data.get('last_name')
            username = form.cleaned_data.get('username')
            email = form.cleaned_data.get('email')
            user = User.objects.get(username=username)
            student = Student(user=user, email=email, first_name=first_name, last_name=last_name)
            student.save()

            if student.pk:
                LOGGER.info(f'Created student with id: {student.pk} associated with auth_user with id: {user.pk}')
            else:
                LOGGER.error(f'Failed to create student to associate with user id: {user.pk}')

            return redirect('student')
        else:
            LOGGER.warning(f'Form not valid: {form.errors}')
        
    context = {
        'form' : form
    }

    return render(request, 'registration/signup.html', context)

@login_required
def student(request):
    userOfReq = request.user

    if not is_student(userOfReq):
        raise PermissionDenied

    if not Student.objects.filter(user=userOfReq).exists():
       return redirect("home")
    if request.method == 'POST' and 'reject_assignment' in request.POST:
        LOGGER.info('Rejecting Assignment...')
        LOGGER.info(request.POST)

        # Process rejection reason
        reason = request.POST['rejection_reason']
        
        # Increment num_graders_needed for the section
        assignment_id = request.POST['assignment_id']
        assignment = Assignment.objects.get(id=assignment_id)
        section = Section.objects.get(id=assignment.section_number_id)
        section.num_graders_needed += 1
        section.save(update_fields=['num_graders_needed'])
        LOGGER.info(f'Incremented num_graders_needed for section with id: {section.id}')

        # Delete the assignment
        status_code = Assignment.objects.filter(id=assignment_id).delete()[0]
        if status_code == 0:
            LOGGER.error(f'Failed to delete assignment with id: {assignment_id}')
        else:
            LOGGER.info(f'Successfully deleted assignment with id: {assignment_id}')

        student_id = request.POST['student_id']
        if reason != 'dont-reassign':
            rejection_reason = request.POST['other_reason']

            # Log reason for rejecting
            rejection_reason_message = rejection_reason if rejection_reason else 'No Reason Given'
            REJECTION_LOGGER.info(f'Student Id {student_id} rejected {section.course_number} with {section.instructor} because: {rejection_reason_message}')

            # Add the student back to the unassigned students table
            new_unassigned_student = UnassignedStudent.objects.create(student_id_id=student_id)
            if not new_unassigned_student.pk:
                LOGGER.error(f'Failed to save new unassigned student with student id: {student_id}')
            else:
                LOGGER.info(f'Successfully saved new unassigned student with student id: {student_id}')
        else:
            LOGGER.info(f'Not adding student id {student_id} back to unassigned students table, student does not want to be a grader anymore')

    # Get signed in user
    user = request.user

    # Get associated student object
    student = Student.objects.filter(user_id=user.id)

    if not student.exists():
        # Handle case where student and user are not propery linked
        LOGGER.error('The student linked with user id: {user.id} does not exist.')
        return server_error(request, '500.html')
    
    LOGGER.info('Student found from signed in user')
    student = student[0]
    # Get assignment(s)
    assignments_objects = Assignment.objects.filter(student_id_id=student.id, status='PENDING')
    assignments = list(assignments_objects)
    LOGGER.info(f'Found {len(assignments)} assignment(s)')

    assigned_sections = []

    # Add the section objects related to the assignments to a list
    for assignment in assignments:
        section_objects = Section.objects.filter(id=assignment.section_number_id)

        if section_objects.exists():
            LOGGER.info(f'Found section associated with section id: {assignment.section_number_id}')
            section = section_objects[0]

            # Get instructor if they are in the database
            instructor = Instructor.objects.filter(id=section.instructor_id)
            instructor = instructor[0] if instructor.exists() else None

            if instructor is None:
                LOGGER.warning(f'Could not find instructor with id: {section.instructor_id}')
            else:
                LOGGER.info('Found instructor for section')

            # get course related to section
            course_object = Course.objects.filter(course_number=section.course_number_id)

            if not course_object.exists():
                LOGGER.warning(f'Could not find course related to section id: {section.course_number_id}')
            else:
                assigned_section = (assignment.id, (course_object[0], section, instructor))
                assigned_sections.append(assigned_section)
                LOGGER.info(f'Assignment: {assigned_section}')

    context = {
        'user' : user,
        'student' : student,
        'assignments' : dict(assigned_sections)
    }

    LOGGER.info(f'Student Context: {context}')

    return render(request, 'student.html', context)

@login_required
def student_intake(request):
    userOfReq = request.user

    if not is_student(userOfReq):
        raise PermissionDenied

    if not Student.objects.filter(user=userOfReq).exists():
       return redirect("home")
    
    context = {}
    messages = {}
    form = ApplicationForm()
    
    if request.method == 'POST':
        form = ApplicationForm(request.POST)
        
        if form.is_valid():
            
            # Update student record in database
            student = Student.objects.filter(user_id=request.user.id)
            if student.exists():
                student = student[0]
                student.in_columbus = form.cleaned_data.get('in_columbus')
                student.previous_grader = form.cleaned_data.get('previous_grader')
                student.graded_last_term = form.cleaned_data.get('prev_class')
                LOGGER.info('updating student record')
                student.save(update_fields=['in_columbus','previous_grader', 'graded_last_term'])
            else:
                LOGGER.error('Student does not exist in the database.')

            # Add student course preferences to database
            student = Student.objects.filter(user_id=request.user.id)
            if student.exists():
                student = student[0]
                course_num_1 = form.cleaned_data.get('preferred_class_1')
                course_instr_1 = form.cleaned_data.get('preferred_class_instr_1')
                course1 = Course.objects.filter(course_number=course_num_1)
                
                if course1.exists():
                    course1 = course1[0]
                    course_1_record = PreviousClassTaken(student_id=student, course_number=course1, instructor=course_instr_1, pref_num=1)
                    course_1_record.save()
                
                course_num_2 = form.cleaned_data.get('preferred_class_2')
                course_instr_2 = form.cleaned_data.get('preferred_class_instr_2')
                course2 = Course.objects.filter(course_number=course_num_2)
                
                if course2.exists():
                    course2 = course2[0]
                    course_2 = PreviousClassTaken(student_id=student, course_number=course2, instructor=course_instr_2, pref_num=2)
                    course_2.save()
                
                course_num_3 = form.cleaned_data.get('preferred_class_3')
                course_instr_3 = form.cleaned_data.get('preferred_class_instr_3')
                course3 = Course.objects.filter(course_number=course_num_3)
                if course3.exists():
                    course3 = course3[0]
                    course_3 = PreviousClassTaken(student_id=student, course_number=course3, instructor=course_instr_3, pref_num=3)
                    course_3.save() 
            else:
                LOGGER.error('Student does not exist in the database.')
            
            # Add student to unassigned students
            unassigned_student = UnassignedStudent(student_id=student)
            unassigned_student.save()
            
            massAssign('SP2024')
            
            return redirect('/thanks/')
        else:
            LOGGER.warn(f'Form is invalid: {form.errors}')
            messages = {"Form is incomplete. Try again."}
            form = ApplicationForm()
            
        context = {
            'application_form': form,
            'messages': messages, 
            }
    else:
        student = Student.objects.get(user_id=request.user.id)
        try:
            unassigned_student = UnassignedStudent.objects.get(student_id=student.id)
            return redirect('/student/')
        except:
            form = ApplicationForm()

    LOGGER.info(f'Intake Form Context: {context}')
    
    return render(request, 'user_intake/application.html', context)

@login_required
def instructor(request):
    user = request.user

    if not is_instructor(user):
        raise PermissionDenied
    
    instructor = Instructor.objects.filter(user_id=user)

    if not instructor.exists():
        LOGGER.error(f'Instructor associated with user {user.username} does not exist, redirecting home')
        return redirect("home")
    
    instructor = instructor[0]

    sections = Section.objects.filter(instructor=instructor)
    # LOGGER.info(f'Sections for this instructor: {sections}')
    
    if(request.method == 'POST'):
            section = Section.objects.filter(section_number = request.POST['section_number'], instructor=instructor)
            if section.exists():
                LOGGER.info('Section Found.')
                section = section[0]
                status = 'PENDING'
                email = request.POST['student_email']
                student = Student.objects.filter(email=email)
                if student.exists():
                    LOGGER.info('Student Found.')
                    student = student[0]
                    assignment = Assignment(section_number=section, status=status, student_id=student)
                    assignment.save()
                    LOGGER.info(f'Assignment for{assignment.section_number.course_number}section {assignment.section_number.section_number} has been saved.')
                    return redirect('/thanks/')
                else:
                    LOGGER.error('Student Not Found.') 
            else:
                LOGGER.error('Section Not Found.')


    context = {
        'sections': sections,
        'instructor': instructor,
        }
    
    LOGGER.info(f'Instructor Context: {context}')

    return render(request, 'instructor.html', context)


@login_required
def instructor_dashboard(request):
    user = request.user
    if not is_instructor(user):
        raise PermissionDenied
    instructor = Instructor.objects.filter(user_id=user)
    if not instructor.exists():
        LOGGER.error(f'Instructor associated with user {user.username} does not exist, redirecting home')
        return redirect("home")
    
    instructor = instructor[0]
    sections = Section.objects.filter(instructor=instructor)
    course_numbers = sections.values_list('course_number', flat=True).distinct()
    courses = Course.objects.filter(course_number__in=course_numbers)

    LOGGER.info(f'Retrieved {courses.count()} courses, {sections.count()} sections, for  instructor {instructor.email} dashboard')

    # Sort the courses by course_number
    sort_direction = 'asc'
    if 'sort' in request.GET:
        sort_direction = request.GET['sort']
        sort_direction = 'asc' if sort_direction == 'desc' else 'desc'

    if sort_direction == 'asc':
        courses = courses.order_by('course_number')
    else:
        courses = courses.order_by('-course_number')

    context = {
        'courses': courses,
        'sections': sections,
       
        'sort_direction': sort_direction,
    }
    
    return render(request, 'administrator.html', context)

@login_required
def instructor_course_detail(request, course_number):
    context = {}
    userOfReq = request.user
    if not is_instructor(userOfReq):
        raise PermissionDenied

    instructor = Instructor.objects.filter(user=userOfReq)
    if instructor.count() <1:
       return redirect("home")
    if request.method == 'POST':
        if 'add_assignment' in request.POST:
            add_assignment(request=request)
    course = Course.objects.get(course_number=course_number)
    sections = Section.objects.filter(course_number=course_number,instructor = instructor[0])
    assignments = Assignment.objects.filter(section_number__course_number=course_number)
    students = Student.objects.filter(assignment__in=assignments)
    context = {
        'course': course,
        'sections': sections,
        'instructors': instructor,
        'assignments': assignments,
        'students': students
    }
    return render(request, 'course_detail.html', context)
