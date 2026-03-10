"""
Scheduled Tasks API Views

Provides REST API endpoints for managing tenant-scoped scheduled Celery tasks.
Includes CRUD operations, execution history, and manual task triggering.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from celery import current_app
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from central_hub.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication
from security.authentication import ServiceJWTAuthentication
from flows.models import ScheduledTask, TaskExecution
from flows.scheduled_task_service import ScheduledTaskService

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class ScheduledTaskViewSet(viewsets.ViewSet):
    """
    ViewSet for managing scheduled tasks.
    
    Endpoints:
    - GET /api/v1/flows/scheduled-tasks/ - List all scheduled tasks
    - POST /api/v1/flows/scheduled-tasks/ - Create a new scheduled task
    - GET /api/v1/flows/scheduled-tasks/{id}/ - Get task details
    - PATCH /api/v1/flows/scheduled-tasks/{id}/ - Update task
    - DELETE /api/v1/flows/scheduled-tasks/{id}/ - Delete task
    - POST /api/v1/flows/scheduled-tasks/{id}/toggle/ - Toggle active state
    - POST /api/v1/flows/scheduled-tasks/{id}/run-now/ - Trigger immediate execution
    - GET /api/v1/flows/scheduled-tasks/{id}/executions/ - View execution history
    - GET /api/v1/flows/scheduled-tasks/available-tasks/ - List available Celery tasks
    """
    
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        ServiceJWTAuthentication,
    ]
    
    def _get_tenant(self, request):
        return getattr(request.user, 'tenant', None)
    
    def _serialize_task(self, task: ScheduledTask) -> dict[str, Any]:
        return {
            'id': str(task.id),
            'name': task.name,
            'description': task.description,
            'task_name': task.task_name,
            'task_args': task.task_args,
            'task_kwargs': task.task_kwargs,
            'schedule_type': task.schedule_type,
            'cron_expression': task.cron_expression,
            'interval_seconds': task.interval_seconds,
            'run_at': task.run_at.isoformat() if task.run_at else None,
            'timezone': task.timezone,
            'status': task.status,
            'is_active': task.is_active,
            'celery_task_name': task.celery_task_name or None,
            'next_run_at': task.next_run_at.isoformat() if task.next_run_at else None,
            'last_run_at': task.last_run_at.isoformat() if task.last_run_at else None,
            'run_count': task.run_count,
            'error_count': task.error_count,
            'created_at': task.created_at.isoformat(),
            'updated_at': task.updated_at.isoformat(),
            'created_by': task.created_by.email if task.created_by else None,
        }
    
    def _serialize_execution(self, execution: TaskExecution) -> dict[str, Any]:
        return {
            'id': str(execution.id),
            'scheduled_task_id': str(execution.scheduled_task_id),
            'status': execution.status,
            'started_at': execution.started_at.isoformat() if execution.started_at else None,
            'finished_at': execution.finished_at.isoformat() if execution.finished_at else None,
            'duration_ms': execution.duration_ms,
            'celery_task_id': execution.celery_task_id,
            'input_data': execution.input_data,
            'result_data': execution.result_data,
            'error_message': execution.error_message,
            'trigger_type': execution.trigger_type,
        }
    
    def list(self, request):
        """List all scheduled tasks for the tenant."""
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        tasks = ScheduledTask.objects.filter(tenant=tenant).order_by('-created_at')
        
        status_filter = request.query_params.get('status')
        if status_filter:
            tasks = tasks.filter(status=status_filter)
        
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            tasks = tasks.filter(is_active=is_active.lower() == 'true')
        
        return Response({
            'tasks': [self._serialize_task(t) for t in tasks],
            'count': tasks.count(),
        })
    
    def create(self, request):
        """Create a new scheduled task."""
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        data = request.data
        
        required_fields = ['name', 'task_name', 'schedule_type']
        for field in required_fields:
            if not data.get(field):
                return Response({'error': f'{field} is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        task = ScheduledTask(
            tenant=tenant,
            name=data['name'],
            description=data.get('description', ''),
            task_name=data['task_name'],
            task_args=data.get('task_args', []),
            task_kwargs=data.get('task_kwargs', {}),
            schedule_type=data['schedule_type'],
            cron_expression=data.get('cron_expression', ''),
            interval_seconds=data.get('interval_seconds'),
            timezone=data.get('timezone', 'UTC'),
            is_active=data.get('is_active', True),
            created_by=request.user if request.user.is_authenticated else None,
        )
        
        if task.schedule_type == ScheduledTask.SCHEDULE_TYPE_ONE_OFF and data.get('run_at'):
            from django.utils.dateparse import parse_datetime
            task.run_at = parse_datetime(data['run_at'])
        
        try:
            task.full_clean()
            task.save()
            
            if task.is_active:
                ScheduledTaskService.sync_task(task)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'success': True,
            'message': 'Scheduled task created successfully',
            'task': self._serialize_task(task),
        }, status=status.HTTP_201_CREATED)
    
    def retrieve(self, request, pk=None):
        """Get a specific scheduled task."""
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        task = get_object_or_404(ScheduledTask, pk=pk, tenant=tenant)
        return Response({'task': self._serialize_task(task)})
    
    def partial_update(self, request, pk=None):
        """Update a scheduled task."""
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        task = get_object_or_404(ScheduledTask, pk=pk, tenant=tenant)
        data = request.data
        
        updatable_fields = [
            'name', 'description', 'task_name', 'task_args', 'task_kwargs',
            'schedule_type', 'cron_expression', 'interval_seconds', 'timezone', 'is_active'
        ]
        
        for field in updatable_fields:
            if field in data:
                setattr(task, field, data[field])
        
        if 'run_at' in data and data['run_at']:
            from django.utils.dateparse import parse_datetime
            task.run_at = parse_datetime(data['run_at'])
        
        try:
            task.full_clean()
            task.save()
            ScheduledTaskService.sync_task(task)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'success': True,
            'message': 'Scheduled task updated successfully',
            'task': self._serialize_task(task),
        })
    
    def destroy(self, request, pk=None):
        """Delete a scheduled task."""
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        task = get_object_or_404(ScheduledTask, pk=pk, tenant=tenant)
        
        ScheduledTaskService.delete_task(task)
        task.delete()
        
        return Response({
            'success': True,
            'message': 'Scheduled task deleted successfully',
        }, status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        """Toggle task active state."""
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        task = get_object_or_404(ScheduledTask, pk=pk, tenant=tenant)
        
        new_state = ScheduledTaskService.toggle_task(task)
        task.refresh_from_db()
        
        return Response({
            'success': True,
            'message': f"Task {'activated' if new_state else 'deactivated'} successfully",
            'is_active': new_state,
            'task': self._serialize_task(task),
        })
    
    @action(detail=True, methods=['post'], url_path='run-now')
    def run_now(self, request, pk=None):
        """Trigger immediate execution of a task."""
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        task = get_object_or_404(ScheduledTask, pk=pk, tenant=tenant)
        
        override_args = request.data.get('args')
        override_kwargs = request.data.get('kwargs')
        
        try:
            execution = ScheduledTaskService.run_task_now(
                task,
                trigger_type='manual',
                override_args=override_args,
                override_kwargs=override_kwargs,
            )
            
            return Response({
                'success': True,
                'message': 'Task execution started',
                'execution': self._serialize_execution(execution),
            })
        except Exception as e:
            logger.exception(f"Failed to run task {task.id}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def executions(self, request, pk=None):
        """Get execution history for a task."""
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        task = get_object_or_404(ScheduledTask, pk=pk, tenant=tenant)
        
        limit = int(request.query_params.get('limit', 50))
        offset = int(request.query_params.get('offset', 0))
        
        executions = TaskExecution.objects.filter(
            scheduled_task=task
        ).order_by('-started_at')[offset:offset + limit]
        
        total_count = TaskExecution.objects.filter(scheduled_task=task).count()
        
        return Response({
            'executions': [self._serialize_execution(e) for e in executions],
            'count': len(executions),
            'total': total_count,
            'limit': limit,
            'offset': offset,
        })
    
    @action(detail=False, methods=['get'], url_path='available-tasks')
    def available_tasks(self, request):
        """List all available Celery tasks that can be scheduled."""
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        tasks = []
        
        try:
            registered_tasks = current_app.tasks
            
            for task_name, task_obj in registered_tasks.items():
                if task_name.startswith('celery.'):
                    continue
                
                doc = task_obj.__doc__ or ''
                
                tasks.append({
                    'name': task_name,
                    'description': doc.strip() if doc else '',
                    'module': getattr(task_obj, '__module__', ''),
                })
            
            tasks.sort(key=lambda x: x['name'])
        except Exception as e:
            logger.exception(f"Failed to list Celery tasks: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'tasks': tasks,
            'count': len(tasks),
        })


@method_decorator(csrf_exempt, name='dispatch')
class TaskExecutionViewSet(viewsets.ViewSet):
    """
    ViewSet for querying task executions across all scheduled tasks.
    
    Endpoints:
    - GET /api/v1/flows/task-executions/ - List all executions with filters
    - GET /api/v1/flows/task-executions/{id}/ - Get execution details
    - GET /api/v1/flows/task-executions/celery-status/{celery_task_id}/ - Query Celery directly
    """
    
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        ServiceJWTAuthentication,
    ]
    
    def _get_tenant(self, request):
        return getattr(request.user, 'tenant', None)
    
    def _serialize_execution(self, execution: TaskExecution) -> dict[str, Any]:
        return {
            'id': str(execution.id),
            'scheduled_task_id': str(execution.scheduled_task_id),
            'scheduled_task_name': execution.scheduled_task.name if execution.scheduled_task else None,
            'task_name': execution.scheduled_task.task_name if execution.scheduled_task else None,
            'status': execution.status,
            'started_at': execution.started_at.isoformat() if execution.started_at else None,
            'finished_at': execution.finished_at.isoformat() if execution.finished_at else None,
            'duration_ms': execution.duration_ms,
            'celery_task_id': execution.celery_task_id,
            'input_data': execution.input_data,
            'result_data': execution.result_data,
            'error_message': execution.error_message,
            'trigger_type': execution.trigger_type,
        }
    
    def list(self, request):
        """List all task executions with optional filters."""
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        executions = TaskExecution.objects.filter(tenant=tenant).select_related('scheduled_task')
        
        # Filter by status
        status_filter = request.query_params.get('status')
        if status_filter:
            executions = executions.filter(status=status_filter)
        
        # Filter by scheduled task ID
        task_id = request.query_params.get('task_id')
        if task_id:
            executions = executions.filter(scheduled_task_id=task_id)
        
        # Filter by task name
        task_name = request.query_params.get('task_name')
        if task_name:
            executions = executions.filter(scheduled_task__task_name__icontains=task_name)
        
        # Filter by trigger type
        trigger_type = request.query_params.get('trigger_type')
        if trigger_type:
            executions = executions.filter(trigger_type=trigger_type)
        
        # Filter by date range
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        if from_date:
            from django.utils.dateparse import parse_datetime
            executions = executions.filter(started_at__gte=parse_datetime(from_date))
        if to_date:
            from django.utils.dateparse import parse_datetime
            executions = executions.filter(started_at__lte=parse_datetime(to_date))
        
        # Pagination
        limit = min(int(request.query_params.get('limit', 50)), 200)
        offset = int(request.query_params.get('offset', 0))
        
        total_count = executions.count()
        executions = executions.order_by('-started_at')[offset:offset + limit]
        
        return Response({
            'executions': [self._serialize_execution(e) for e in executions],
            'count': len(executions),
            'total': total_count,
            'limit': limit,
            'offset': offset,
        })
    
    def retrieve(self, request, pk=None):
        """Get detailed execution information."""
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        execution = get_object_or_404(
            TaskExecution.objects.select_related('scheduled_task'),
            pk=pk,
            tenant=tenant
        )
        
        data = self._serialize_execution(execution)
        data['error_traceback'] = execution.error_traceback
        
        return Response({'execution': data})
    
    @action(detail=False, methods=['get'], url_path='celery-status/(?P<celery_task_id>[^/.]+)')
    def celery_status(self, request, celery_task_id=None):
        """
        Query Celery directly for real-time task status.
        Returns the current state of the Celery task by its task ID.
        """
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            from celery.result import AsyncResult
            
            result = AsyncResult(celery_task_id)
            
            response_data = {
                'celery_task_id': celery_task_id,
                'state': result.state,
                'ready': result.ready(),
                'successful': result.successful() if result.ready() else None,
                'failed': result.failed() if result.ready() else None,
            }
            
            # Include result if task completed successfully
            if result.ready() and result.successful():
                try:
                    response_data['result'] = result.result
                except Exception:
                    response_data['result'] = str(result.result)
            
            # Include error info if task failed
            if result.failed():
                response_data['error'] = str(result.result) if result.result else None
                response_data['traceback'] = result.traceback
            
            # Try to find matching TaskExecution record
            execution = TaskExecution.objects.filter(
                celery_task_id=celery_task_id,
                tenant=tenant
            ).first()
            
            if execution:
                response_data['execution_id'] = str(execution.id)
                response_data['scheduled_task_id'] = str(execution.scheduled_task_id)
                response_data['scheduled_task_name'] = execution.scheduled_task.name if execution.scheduled_task else None
            
            return Response(response_data)
            
        except Exception as e:
            logger.exception(f"Failed to query Celery task {celery_task_id}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='running')
    def running(self, request):
        """List currently running task executions."""
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        executions = TaskExecution.objects.filter(
            tenant=tenant,
            status__in=[TaskExecution.STATUS_PENDING, TaskExecution.STATUS_RUNNING]
        ).select_related('scheduled_task').order_by('-started_at')[:50]
        
        return Response({
            'executions': [self._serialize_execution(e) for e in executions],
            'count': len(executions),
        })
    
    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """Get execution statistics for the tenant."""
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        from django.db.models import Count, Avg
        
        # Get counts by status
        status_counts = TaskExecution.objects.filter(
            tenant=tenant
        ).values('status').annotate(count=Count('id'))
        
        status_dict = {item['status']: item['count'] for item in status_counts}
        
        # Get average duration for successful tasks
        avg_duration = TaskExecution.objects.filter(
            tenant=tenant,
            status=TaskExecution.STATUS_SUCCESS,
            duration_ms__isnull=False
        ).aggregate(avg_duration=Avg('duration_ms'))
        
        # Recent failures (last 24 hours)
        from datetime import timedelta
        recent_failures = TaskExecution.objects.filter(
            tenant=tenant,
            status=TaskExecution.STATUS_FAILED,
            started_at__gte=timezone.now() - timedelta(hours=24)
        ).count()
        
        return Response({
            'total': sum(status_dict.values()),
            'by_status': status_dict,
            'avg_duration_ms': avg_duration['avg_duration'],
            'recent_failures_24h': recent_failures,
        })
