"""
User Context Manager - High-performance user context caching

Caches user language and preferences at the context level to avoid
repeated database queries during a single session.

This middleware reduces database calls from 100+ per session to ~1-3.
"""

import logging
import time
from typing import Optional, Dict, Any
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Context keys for user data
USER_LANG_KEY = '_cached_user_lang'
USER_LANG_TIMESTAMP_KEY = '_cached_user_lang_ts'
USER_CONTEXT_KEY = '_cached_user_context'
CONTEXT_CACHE_TTL = 3600  # 1 hour cache TTL


async def get_user_language_cached(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE
) -> str:
    """
    Get user language with context-level caching.
    
    This function caches the user's language preference in the context
    to avoid repeated database queries within the same session.
    
    Args:
        update: Telegram Update object
        context: Bot context with user_data
        
    Returns:
        User's language code (defaults to 'en')
    """
    from localization import resolve_user_language, LanguageConfig
    
    # Get user info
    user = update.effective_user
    if not user:
        return LanguageConfig.DEFAULT_LANGUAGE
    
    user_id = user.id
    telegram_lang = getattr(user, 'language_code', None)
    
    # Check context cache first
    if context.user_data:
        cached_lang = context.user_data.get(USER_LANG_KEY)
        cached_ts = context.user_data.get(USER_LANG_TIMESTAMP_KEY, 0)
        
        # Use cache if valid and not expired
        if cached_lang and (time.time() - cached_ts) < CONTEXT_CACHE_TTL:
            logger.debug(f"⚡ Context cache HIT for user {user_id} lang: {cached_lang}")
            return cached_lang
    
    # Cache miss - resolve from database/telegram
    try:
        user_lang = await resolve_user_language(user_id, telegram_lang)
        
        # Store in context cache
        if context.user_data is not None:
            context.user_data[USER_LANG_KEY] = user_lang
            context.user_data[USER_LANG_TIMESTAMP_KEY] = time.time()
            logger.debug(f"💾 Context cache SET for user {user_id}: {user_lang}")
        
        return user_lang
        
    except Exception as e:
        logger.warning(f"Failed to resolve user language for {user_id}: {e}")
        return LanguageConfig.DEFAULT_LANGUAGE


def invalidate_user_language_cache(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Invalidate the user language cache in context.
    
    Call this when the user explicitly changes their language preference.
    """
    if context.user_data:
        context.user_data.pop(USER_LANG_KEY, None)
        context.user_data.pop(USER_LANG_TIMESTAMP_KEY, None)
        logger.debug("🗑️ User language context cache invalidated")


async def get_user_context_cached(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> Dict[str, Any]:
    """
    Get comprehensive user context with caching.
    
    Returns a dict containing:
    - user_lang: User's preferred language
    - user_id: Telegram user ID
    - is_admin: Whether user is an admin
    - username: User's username (if available)
    
    All values are cached at the context level for performance.
    """
    from localization import resolve_user_language
    
    user = update.effective_user
    if not user:
        return {
            'user_lang': 'en',
            'user_id': 0,
            'is_admin': False,
            'username': None
        }
    
    # Check for cached context
    if context.user_data:
        cached_context = context.user_data.get(USER_CONTEXT_KEY)
        if cached_context:
            cached_ts = cached_context.get('_timestamp', 0)
            if (time.time() - cached_ts) < CONTEXT_CACHE_TTL:
                logger.debug(f"⚡ Full context cache HIT for user {user.id}")
                return cached_context
    
    # Build fresh context
    user_lang = await get_user_language_cached(update, context)
    
    # Check admin status (import here to avoid circular imports)
    try:
        from database import is_user_admin
        is_admin = await is_user_admin(user.id)
    except Exception:
        is_admin = False
    
    user_context = {
        'user_lang': user_lang,
        'user_id': user.id,
        'is_admin': is_admin,
        'username': user.username,
        'first_name': user.first_name,
        '_timestamp': time.time()
    }
    
    # Store in context
    if context.user_data is not None:
        context.user_data[USER_CONTEXT_KEY] = user_context
        logger.debug(f"💾 Full context cache SET for user {user.id}")
    
    return user_context


def clear_user_context_cache(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear all cached user context data"""
    if context.user_data:
        context.user_data.pop(USER_LANG_KEY, None)
        context.user_data.pop(USER_LANG_TIMESTAMP_KEY, None)
        context.user_data.pop(USER_CONTEXT_KEY, None)
        logger.debug("🗑️ All user context caches cleared")


# ============================================================================
# Decorator for automatic language resolution
# ============================================================================

def with_user_lang(func):
    """
    Decorator that automatically resolves user language and passes it to handler.
    
    Usage:
        @with_user_lang
        async def my_handler(update, context, user_lang):
            # user_lang is automatically resolved and cached
            await update.message.reply_text(t("greeting", user_lang))
    """
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_lang = await get_user_language_cached(update, context)
        return await func(update, context, user_lang, *args, **kwargs)
    
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


def with_user_context(func):
    """
    Decorator that provides full user context to handler.
    
    Usage:
        @with_user_context
        async def my_handler(update, context, user_ctx):
            user_lang = user_ctx['user_lang']
            is_admin = user_ctx['is_admin']
            # ... use context
    """
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_ctx = await get_user_context_cached(update, context)
        return await func(update, context, user_ctx, *args, **kwargs)
    
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper
